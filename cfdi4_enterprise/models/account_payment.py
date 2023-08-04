from odoo import _, api, fields, models

import base64
from datetime import datetime
from itertools import groupby
import logging
import requests
import json
from lxml import etree
from lxml.objectify import fromstring
from zeep import Client
from zeep.transports import Transport
from odoo import _, api, fields, models
from odoo.tools import DEFAULT_SERVER_TIME_FORMAT, float_is_zero
from odoo.tools.float_utils import float_compare
from odoo.tools.misc import html_escape
from odoo.exceptions import UserError

from . import account_move

_logger = logging.getLogger(__name__)

CFDI_TEMPLATE = 'cfdi4_enterprise.payment20'
CFDI_XSLT_CADENA = 'cfdi4_enterprise/data/4.0/cadenaoriginal.xslt'
CFDI_XSLT_CADENA_TFD = 'cfdi4_enterprise/data/xslt/4.0/cadenaoriginal_TFD_1_1.xslt'


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_process_edi_web_services(self):
        vals = super(AccountPayment, self).action_process_edi_web_services()
        self.update_values_tax()
        return vals


    @api.model
    def _get_l10n_mx_edi_cadena(self):
        self.ensure_one()
        # get the xslt path
        xslt_path = CFDI_XSLT_CADENA_TFD
        # get the cfdi as eTree
        cfdi = base64.decodebytes(self.l10n_mx_edi_cfdi)
        cfdi = self.l10n_mx_edi_get_xml_etree(cfdi)
        cfdi = self.l10n_mx_edi_get_tfd_etree(cfdi)
        # return the cadena
        return self.env['account.move'].l10n_mx_edi_generate_cadena(xslt_path, cfdi)

    def _l10n_mx_edi_create_cfdi_payment(self):
        self.ensure_one()
        qweb = self.env['ir.qweb']
        error_log = []
        company_id = self.company_id
        pac_name = company_id.l10n_mx_edi_pac
        values = self._l10n_mx_edi_create_cfdi_values()
        if 'error' in values:
            error_log.append(values.get('error'))

        # -----------------------
        # Check the configuration
        # -----------------------
        # -Check certificate
        certificate_ids = company_id.l10n_mx_edi_certificate_ids
        certificate_id = certificate_ids.sudo().get_valid_certificate()
        if not certificate_id:
            error_log.append(_('No valid certificate found'))

        # -Check PAC
        if pac_name:
            pac_test_env = company_id.l10n_mx_edi_pac_test_env
            pac_password = company_id.l10n_mx_edi_pac_password
            if not pac_test_env and not pac_password:
                error_log.append(_('No PAC credentials specified.'))
        else:
            error_log.append(_('No PAC specified.'))

        if error_log:
            return {'error': _('Please check your configuration: ') + account_invoice.create_list_html(error_log)}

        # -Compute date and time of the invoice
        partner = self.journal_id.l10n_mx_address_issued_id or self.company_id.partner_id.commercial_partner_id
        tz = self.env['account.move']._l10n_mx_edi_get_timezone(
            partner.state_id.code)
        date_mx = datetime.now(tz)
        if not self.l10n_mx_edi_expedition_date:
            self.l10n_mx_edi_expedition_date = date_mx.date()
        if not self.l10n_mx_edi_time_payment:
            self.l10n_mx_edi_time_payment = date_mx.strftime(
                DEFAULT_SERVER_TIME_FORMAT)

        time_invoice = datetime.strptime(self.l10n_mx_edi_time_payment,
                                         DEFAULT_SERVER_TIME_FORMAT).time()

        # -----------------------
        # Create the EDI document
        # -----------------------

        # -Compute certificate data
        values['date'] = datetime.combine(
            fields.Datetime.from_string(self.l10n_mx_edi_expedition_date),
            time_invoice).strftime('%Y-%m-%dT%H:%M:%S')
        values['certificate_number'] = certificate_id.serial_number
        values['certificate'] = certificate_id.sudo().get_data()[0]

        # -Compute cfdi
        cfdi = qweb.render(CFDI_TEMPLATE, values=values)

        # -Compute cadena
        tree = self.l10n_mx_edi_get_xml_etree(cfdi)
        cadena = self.env['account.move'].l10n_mx_edi_generate_cadena(
            CFDI_XSLT_CADENA, tree)

        # Post append cadena
        tree.attrib['Sello'] = certificate_id.sudo().get_encrypted_cadena(cadena)

        # TODO - Check with XSD
        return {'cfdi': etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding='UTF-8')}

    account_payment_tax_ids = fields.One2many(
        'account.payment.tax',
        'account_payment_id',
        string='Linea impuestos',
        ondelete="cascade"
    )



    def update_values_tax(self):
        for rec in self:
            print("sxss")
            tax = self.env['account.payment.tax']
            rec.account_payment_tax_ids.unlink()
            if rec.reconciled_invoice_ids:
                for r in rec.reconciled_invoice_ids:
                    print("r.tax_totals_json",r.name)
                    invoice_totals = json.loads(r.tax_totals_json)
                    for tax in invoice_totals['groups_by_subtotal'].values():
                        for amount_by_group in tax:
                           
                            tax = self.env["account.tax"].search([('tax_group_id', '=', amount_by_group['tax_group_id']),('type_tax_use', '=', 'sale')], limit=1) 
                            print("amount_by_group['tax_group_amount']",amount_by_group['tax_group_amount'],tax)                       
                            if amount_by_group['tax_group_amount'] > 0:
                                if amount_by_group['tax_group_amount'] > 0:
                                    vals = {
                                        'type_impuestos': 'trasladodr',
                                        'base': amount_by_group['tax_group_base_amount'],
                                        'impuesto': '002',
                                        'tipofactor': tax.l10n_mx_tax_type,
                                        'tasacuota': tax.amount,
                                        'importe': amount_by_group['tax_group_amount'],
                                        'invoice_id': r.id,
                                        'account_payment_id': rec.id,
                                    }
                                    self.env['account.payment.tax'].create(vals)
                            if amount_by_group['tax_group_amount'] < 0:
                                if amount_by_group['tax_group_base_amount'] > 0:
                                    vals = {
                                        'type_impuestos': 'retencionesdr',
                                        'base': amount_by_group['tax_group_base_amount'],
                                        'impuesto': '002',
                                        'tipofactor': tax.l10n_mx_tax_type,
                                        'tasacuota': tax.amount,
                                        'importe': amount_by_group['tax_group_amount'],
                                        'invoice_id': r.id,
                                        'account_payment_id': rec.id,
                                    }
                                    self.env['account.payment.tax'].create(vals)