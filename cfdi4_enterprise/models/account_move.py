# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.float_utils import float_repr
import xmlrpc.client
import base64
import requests
import json
from lxml import etree
from lxml.objectify import fromstring
from odoo.tools import DEFAULT_SERVER_TIME_FORMAT
from odoo.tools.xml_utils import _check_with_xsd
from pytz import timezone
from datetime import datetime
from dateutil.relativedelta import relativedelta

CFDI_TEMPLATE_33 = 'cfdi4_enterprise.cfdiv40'
CFDI_XSLT_CADENA = 'cfdi4_enterprise/data/4.0/cadenaoriginal.xslt'
CFDI_XSLT_CADENA_TFD = 'cfdi4_enterprise/data/xslt/4.0/cadenaoriginal_TFD_1_1.xslt'


import logging
_logger = logging.getLogger(__name__)


def create_list_html(array):
    '''Convert an array of string to a html list.
    :param array: A list of strings
    :return: an empty string if not array, an html list otherwise.
    '''
    if not array:
        return ''
    msg = ''
    for item in array:
        msg += '<li>' + item + '</li>'
    return '<ul>' + msg + '</ul>'


class AccountMove(models.Model):
    _inherit = "account.move"

    

    #### Migracion  ######


    def _l10n_mx_edi_decode_cfdi(self, cfdi_data=None):
        ''' Helper to extract relevant data from the CFDI to be used, for example, when printing the invoice.
        :param cfdi_data:   The optional cfdi data.
        :return:            A python dictionary.
        '''
        self.ensure_one()

        def get_node(cfdi_node, attribute, namespaces):
            if hasattr(cfdi_node, 'Complemento'):
                node = cfdi_node.Complemento.xpath(attribute, namespaces=namespaces)
                return node[0] if node else None
            else:
                return None

        def get_cadena(cfdi_node, template):
            if cfdi_node is None:
                return None
            cadena_root = etree.parse(tools.file_open(template))
            return str(etree.XSLT(cadena_root)(cfdi_node))

        # Find a signed cfdi.
        if not cfdi_data:
            #signed_edi = self._get_l10n_mx_edi_signed_edi_document()
            signed_edi = self._get_l10n_mx_edi_signed_edi_document_4_0()
            if signed_edi:
                cfdi_data = base64.decodebytes(signed_edi.attachment_id.with_context(bin_size=False).datas)

        # Nothing to decode.
        if not cfdi_data:
            return {}

        cfdi_node = fromstring(cfdi_data)
        tfd_node = get_node(
            cfdi_node,
            'tfd:TimbreFiscalDigital[1]',
            {'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'},
        )

        return {
            'uuid': ({} if tfd_node is None else tfd_node).get('UUID'),
            'supplier_rfc': cfdi_node.Emisor.get('Rfc', cfdi_node.Emisor.get('rfc')),
            'customer_rfc': cfdi_node.Receptor.get('Rfc', cfdi_node.Receptor.get('rfc')),
            'amount_total': cfdi_node.get('Total', cfdi_node.get('total')),
            'cfdi_node': cfdi_node,
            'usage': cfdi_node.Receptor.get('UsoCFDI'),
            'payment_method': cfdi_node.get('formaDePago', cfdi_node.get('MetodoPago')),
            'bank_account': cfdi_node.get('NumCtaPago'),
            'sello': cfdi_node.get('sello', cfdi_node.get('Sello', 'No identificado')),
            'sello_sat': tfd_node is not None and tfd_node.get('selloSAT', tfd_node.get('SelloSAT', 'No identificado')),
            'cadena': tfd_node is not None and get_cadena(tfd_node, CFDI_XSLT_CADENA_TFD) or get_cadena(cfdi_node, CFDI_XSLT_CADENA),
            'certificate_number': cfdi_node.get('noCertificado', cfdi_node.get('NoCertificado')),
            'certificate_sat_number': tfd_node is not None and tfd_node.get('NoCertificadoSAT'),
            'expedition': cfdi_node.get('LugarExpedicion'),
            'fiscal_regime': cfdi_node.Emisor.get('RegimenFiscal', ''),
            'emission_date_str': cfdi_node.get('fecha', cfdi_node.get('Fecha', '')).replace('T', ' '),
            'stamp_date': tfd_node is not None and tfd_node.get('FechaTimbrado', '').replace('T', ' '),
        }

    def _get_l10n_mx_edi_signed_edi_document_4_0(self):
        self.ensure_one()

        cfdi_4_4_edi = self.env.ref('cfdi4_enterprise.edi_cfdi_4_0')
        return self.edi_document_ids.filtered(lambda document: document.edi_format_id == cfdi_4_4_edi and document.attachment_id)

    def l10n_mx_edi_update_sat_status(self):
        '''Synchronize both systems: Odoo & SAT to make sure the invoice is valid.
        '''
        for move in self:
            supplier_rfc = move.l10n_mx_edi_cfdi_supplier_rfc
            customer_rfc = move.l10n_mx_edi_cfdi_customer_rfc
            total = float_repr(move.l10n_mx_edi_cfdi_amount, precision_digits=move.currency_id.decimal_places)
            uuid = move.l10n_mx_edi_cfdi_uuid

            # If the CFDI attachment was unlinked from the edi_document (e.g. when canceling the invoice),
            # the l10n_mx_edi_cfdi_uuid, ... fields will have been set to False.
            # However, the attachment might still be there, so try to retrieve it.
            cfdi_doc = move.edi_document_ids.filtered(lambda document: document.edi_format_id == self.env.ref('cfdi4_enterprise.edi_cfdi_4_0'))
            if cfdi_doc and not cfdi_doc.attachment_id:
                attachment = self.env['ir.attachment'].search([('name', 'like', '%-MX-Invoice-4.0.xml'), ('res_model', '=', 'account.move'), ('res_id', '=', move.id)], limit=1, order='create_date desc')
                if attachment:
                    cfdi_data = base64.decodebytes(attachment.with_context(bin_size=False).datas)
                    cfdi_infos = move._l10n_mx_edi_decode_cfdi(cfdi_data=cfdi_data)
                    uuid = cfdi_infos['uuid']
                    supplier_rfc = cfdi_infos['supplier_rfc']
                    customer_rfc = cfdi_infos['customer_rfc']
                    total = cfdi_infos['amount_total']

            try:
                status = self.env['account.edi.format']._l10n_mx_edi_get_sat_status(supplier_rfc, customer_rfc, total, uuid)
            except Exception as e:
                move.message_post(body=_("Failure during update of the SAT status: %(msg)s", msg=str(e)))
                continue

            if status == 'Vigente':
                move.l10n_mx_edi_sat_status = 'valid'
            elif status == 'Cancelado':
                move.l10n_mx_edi_sat_status = 'cancelled'
            elif status == 'No Encontrado':
                move.l10n_mx_edi_sat_status = 'not_found'
            else:
                move.l10n_mx_edi_sat_status = 'none'


    @api.model
    def _l10n_mx_edi_cron_update_sat_status(self):
        ''' Call the SAT to know if the invoice is available government-side or if the invoice has been cancelled.
        In the second case, the cancellation could be done Odoo-side and then we need to check if the SAT is up-to-date,
        or could be done manually government-side forcing Odoo to update the invoice's state.
        '''

        # Update the 'l10n_mx_edi_sat_status' field.
        cfdi_edi_format = self.env.ref('cfdi4_enterprise.edi_cfdi_4_0')
        to_process = self.env['account.edi.document'].search([
            ('edi_format_id', '=', cfdi_edi_format.id),
            ('state', 'in', ('sent', 'cancelled')),
            ('move_id.l10n_mx_edi_sat_status', 'in', ('undefined', 'not_found', 'none')),
        ])
        to_process.move_id.l10n_mx_edi_update_sat_status()

        # Handle the case when the invoice has been cancelled manually government-side.
        to_process\
            .filtered(lambda doc: doc.state == 'sent' and doc.move_id.l10n_mx_edi_sat_status == 'cancelled')\
            .move_id\
            .button_cancel()

    def get_new_cfdi_fields(self, name):
        if name == 'Exportacion':
            return "01"
        if name == 'FacAtrAdquirente':
            return False


    l10n_mx_edi_usage = fields.Selection(
        selection=[
            ('G01', 'Adquisición de mercancías'),
            ('G02', 'Devoluciones, descuentos o bonificaciones'),
            ('G03', 'Gastos generales'),
            ('I01', 'Construcciones'),
            ('I02', 'Inversión en mobiliario y equipo de oficina'),
            ('I03', 'Equipo de transporte'),
            ('I04', 'Equipos informáticos y accesorios'),
            ('I05', 'Cuadros, matrices, moldes, matrices y utillajes'),
            ('I06', 'Comunicaciones telefónicas'),
            ('I07', 'Comunicaciones por satélite'),
            ('I08', 'Otra maquinaria y equipo'),
            ('D01', 'Gastos médicos, dentales y de hospital.'),
            ('D02', 'Gastos médicos por invalidez'),
            ('D03', 'Gastos funerarios'),
            ('D04', 'Donaciones'),
            ('D05', 'Intereses reales efectivamente pagados por préstamos hipotecarios (habitación)'),
            ('D06', 'Contribuciones voluntarias al SAR'),
            ('D07', 'Primas de seguro médico'),
            ('D08', 'Gastos de Transporte Escolar Obligatorio'),
            ('D09', 'Depósitos en cuentas de ahorro, primas en base a planes de pensiones.'),
            ('D10', 'Pagos por servicios educativos (Colegiatura)'),
            ('S01', 'Sin efectos fiscales'),
            ('P01', 'Por definir'),
        ],
        string="Usage",
        default='P01',)

    def xxxx(self,xx):
        print("xxx ------------- account_move_values xxxx ----------------------------xx",xx)

    def xxx(self,xx):
        print("xxx ------------- account_move_values xxx ----------------------------xx",type(xx),xx['tax_group_name'])
        for xx in xx:
            print("xxx .........",xx[0])

    def account_move_values(self,ids):
        account = self.env["account.move"].search([('id', '=', ids)], limit=1)
        print("xxx account xxx",account)
        vals = []
        for inv in account:
            print("xxxx",inv.tax_totals_json)
            invoice_totals = json.loads(inv.tax_totals_json)
            for tax in invoice_totals['groups_by_subtotal'].values():
                for amount_by_group in tax:
                    print("+++++++++++ amount_by_group ++++++++++++++",amount_by_group)
                    vals.append(amount_by_group)
        print("+++++++++++ vals ++++++++++++++",vals)
        for v in vals:
            print("xvx",v['tax_group_name'])
        return vals

    def account_move_tax(self,ids):
        tax = self.env["account.tax"].search([('tax_group_id', '=', ids),('type_tax_use', '=', 'sale')], limit=1)
        print("xx account_move_tax xx",tax)        
        return tax

    def account_move_ObjetoImpDR(self,vals):
        imp = 0
        
        if vals['ivatra08'] != 0:
            imp += 1
        if vals['ivatra16'] != 0:
            imp += 1
        if vals['retiva'] * -1 !=0:
            imp += 1
        if vals['retisr'] * -1 != 0:
            imp += 1
        print("account_move_ObjetoImpDR",imp,vals)
        if imp >= 1:
            return '02'
        else:
            return '01'


    def account_move_tax_totals(self,invoice,currency):
        retiva = 0
        retisr = 0
        ivabase16 = 0
        ivatra16 = 0
        ivabase08 = 0
        ivatra08 = 0
        for rec in invoice:
            print("xxx inv xxx",rec)
            for inv in rec['invoice']:
                print("xxxx",inv.tax_totals_json)
                invoice_totals = json.loads(inv.tax_totals_json)
                for tax in invoice_totals['groups_by_subtotal'].values():
                    for amount_by_group in tax:
                        print("amount_by_group['tax_group_name']",amount_by_group['tax_group_name'])
                        if amount_by_group['tax_group_name'].strip() == "IVA 16%":
                            ivabase16 += amount_by_group['tax_group_base_amount']
                            ivatra16 += amount_by_group['tax_group_amount']
                        if amount_by_group['tax_group_name'].strip() == "IVA Retencion 10.67%":
                            retiva += amount_by_group['tax_group_amount']
                        if amount_by_group['tax_group_name'].strip() == "ISR Retencion 10%":
                            retisr += amount_by_group['tax_group_amount']

                        if amount_by_group['tax_group_name'] == "IVA 8%":
                            ivabase08 += amount_by_group['tax_group_base_amount']
                            ivatra08 += amount_by_group['tax_group_amount']
               

        if self.currency_id.name == 'MXN':

            vals = {
                'ivabase08':ivabase08,
                'ivatra08':ivatra08,
                'ivabase16':ivabase16,
                'ivatra16':ivatra16,
                'retiva': retiva,
                'retisr': retisr,
            }
        else:
            vals = {
                'ivabase08': round(float(ivabase08) / float(currency),2),
                'ivatra08':round(float(ivatra08) / float(currency),2),
                'ivabase16': round(float(ivabase16) / float(currency),2),
                'ivatra16':round(float(ivatra16) / float(currency),2),
                'retiva': round(float(retiva) / float(currency),2),
                'retisr': round(float(retisr) / float(currency),2),
            }
        print("zxxxx",vals)                       
        return vals

    l10n_mx_edi_usage = fields.Selection(
        selection_add=[
            ('S01', 'Sin efectos fiscales.'),
            ('CP01', 'Pagos'),
            ('CN01', 'Nómina'),
        ])


    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id.l10n_mx_edi_usage:
            self.l10n_mx_edi_usage = self.partner_id.l10n_mx_edi_usage
        else:
            self.l10n_mx_edi_usage = ''
        if self.partner_id.l10n_mx_edi_payment_method_id:
            self.write({'l10n_mx_edi_payment_method_id':self.partner_id.l10n_mx_edi_payment_method_id.id })
        else:
            self.write({'l10n_mx_edi_payment_method_id':False})
        return super(AccountMove, self)._onchange_partner_id()



    def edi_cfdi40(self):
        for rec in self:

            try:
                url = rec.company_id.edi_url_bd
                db = rec.company_id.edi_name_bd
                username = rec.company_id.edi_user_bd
                password = rec.company_id.edi_passw_bd
                common = xmlrpc.client.ServerProxy(
                        '{}/xmlrpc/2/common'.format(url))
                uid = common.authenticate(db, username, password, {})
                models = xmlrpc.client.ServerProxy(
                    '{}/xmlrpc/2/object'.format(url))
                response = {}
                
                
                model_name = 'sign.account.move'

                edi_user_pac = rec.company_id.edi_user_pac
                edi_pass_pac = rec.company_id.edi_pass_pac
                
                json_data = {'name': rec.name}
                print("DATA TO CANCEL: ", json_data, username, password)
                response = models.execute_kw(
                    db, uid, password, model_name, 'request_cfd40', [False, json_data, edi_user_pac, edi_pass_pac])
                if response:
                    rec.message_post(body=_(
                        """<p>Conexion correcta</p>"""))
                    return response
                else:
                    rec.message_post(body=_(
                        """<p>Error, No existe el usuario</p>"""))

            except Exception as err:
                rec.message_post(body=_(
                    """<p>La conexion falló.</p><p><ul>%s</ul></p>""" % err))