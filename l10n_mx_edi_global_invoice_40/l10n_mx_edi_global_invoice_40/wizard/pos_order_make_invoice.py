# -*- coding: utf-8 -*-

import time

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import float_is_zero
import datetime
import logging
_log = logging.getLogger("___name: %s" % __name__)
from odoo.exceptions import ValidationError, UserError
from itertools import groupby
from operator import itemgetter


class PosOrderMakeInv(models.TransientModel):
    _name = 'pos.order.make.inv'
    _description = "Modelo que crea las facturas globales"

    count = fields.Integer(string="Numero de órdenes", compute='_compute_count')
    pos_order_ids = fields.Many2many(
        'pos.order', default=lambda self: self.env.context.get('active_ids'))


    periodicidad = fields.Selection([
            ('01', 'Diario'),
            ('02', 'Semanal'),
            ('03', 'Quincenal'),
            ('04', 'Mensual'),
        ], 'Periodicidad',
        default='01')

    fecha_factura = fields.Date("Fecha de factura", default=lambda self: fields.Date.context_today(self))
    meses = fields.Selection([
        ('01', 'Enero'),
        ('02', 'Febrero'),
        ('03', 'Marzo'),
        ('04', 'Abril'),
        ('05', 'Mayo'),
        ('06', 'Junio'),
        ('07', 'Julio'),
        ('08', 'Agosto'),
        ('09', 'Septiempre'),
        ('10', 'Octubre'),
        ('11', 'Noviembre'),
        ('12', 'Diciembre'),
        ], 'Mes',
        default=datetime.datetime.now().strftime("%m"))
    year = fields.Integer('Año',
        default=datetime.datetime.now().strftime("%Y"))

    product_id = fields.Many2one(
        comodel_name='product.product',
        string="Producto Utilizado",
        compute='_compute_product_id',
        readonly=False,
        store=True)

    l10n_mx_edi_payment_method_id = fields.Many2one(
        comodel_name='l10n_mx_edi.payment.method',
        string="Metodo de pago",
        compute='_compute_metodo_pago_id',
        readonly=False,
        store=True)

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string="Diario",
        compute='_compute_journal_id',
        readonly=False,
        store=True,domain=[('type','=','sale')])
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string="Cliente",
        compute='_compute_partner_id',
        readonly=False,
        store=True)
    amount = fields.Float(
        string="Monto Total de las ordenes seleccionadas",
        help="Suma total de las ordenes.",
        compute='_compute_amount_total',
        store=True
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        compute='_compute_currency_id',
        store=True)
    company_id = fields.Many2one(
        comodel_name='res.company',
        compute='_compute_company_id',
        store=True)


    #=== COMPUTE METHODS ===#

    @api.depends('pos_order_ids')
    def _compute_count(self):
        for wizard in self:
            wizard.count = len(wizard.pos_order_ids)

    @api.depends('pos_order_ids')
    def _compute_currency_id(self):
        for wizard in self:
            currencys = set()
            for pos_order in wizard.pos_order_ids:
                currencys.add(pos_order.currency_id.id)
            _log.info("Currencys found %s",currencys)
            if len(currencys) == 1:
                wizard.currency_id = list(currencys)[0]

    @api.depends('pos_order_ids')
    def _compute_amount_total(self):
        for wizard in self:
            wizard.amount = sum([pos.amount_total for pos in wizard.pos_order_ids])

    @api.depends('pos_order_ids')
    def _compute_company_id(self):
        self.company_id = False
        for wizard in self:
            if wizard.pos_order_ids:
                wizard.company_id = wizard.pos_order_ids[0].company_id.id
                continue

    @api.depends('company_id')
    def _compute_product_id(self):
        self.product_id = False
        for wizard in self:
            if wizard.company_id and wizard.company_id.product_inv_global_id:
                wizard.product_id = wizard.company_id.product_inv_global_id.id

    @api.depends('company_id')
    def _compute_journal_id(self):
        self.journal_id = False
        for wizard in self:
            if wizard.company_id and wizard.company_id.journal_inv_global_id:
                wizard.journal_id = wizard.company_id.journal_inv_global_id.id

    @api.depends('company_id')
    def _compute_partner_id(self):
        self.partner_id = False
        for wizard in self:
            if wizard.company_id and wizard.company_id.partner_inv_global_id:
                wizard.partner_id = wizard.company_id.partner_inv_global_id.id

    @api.depends('company_id')
    def _compute_metodo_pago_id(self):
        for wizard in self:
            forma_pago = {}
            for line in self.pos_order_ids:
                for l in line.payment_ids:
                    if l.payment_method_id in forma_pago:
                        forma_pago[l.payment_method_id] += l.amount
                    else:
                        forma_pago[l.payment_method_id] = l.amount
            if forma_pago:
                l10n_mx_edi_payment_method_id = max(forma_pago.items(), key=lambda x: x[1])[0]
                wizard.l10n_mx_edi_payment_method_id = l10n_mx_edi_payment_method_id.l10n_mx_edi_payment_method_id.id or False
            else:
                wizard.l10n_mx_edi_payment_method_id = False


    def get_invoice_lines_from_pos_orders(self):
        pre_invoice_line_ids = []

        for order in self.pos_order_ids:
            pre_invoice_line_ids += order._prepare_invoice_line_global(order.pos_reference)



        product_uom_activity = self.product_id.uom_id
        product_product_sell = self.product_id

        grouper = itemgetter('name','tax_ids', 'discount')
        result = []

        for key, grp in groupby(sorted(pre_invoice_line_ids, key=grouper), grouper):
            temp_dict = dict(zip(['name', 'tax_ids', 'discount'], key))

            temp_dict['price_unit'] = 0
            for item in grp:
                temp_dict['price_unit'] += item['price_unit'] * item['quantity']
                if 'name' not in temp_dict:
                    temp_dict['name'] = item['name']

            temp_dict['quantity'] = 1
            temp_dict['product_id'] = product_product_sell.id
            temp_dict['product_uom_id'] = product_uom_activity.id
            result.append((0,None,temp_dict))

        return result


    #=== ACTION METHODS ===#

    def create_invoices(self):
        self.ensure_one()
        orders_incorrectas = self.pos_order_ids.filtered(lambda x: x.state not in ['paid', 'done'])
        if len(orders_incorrectas) > 0:
            str_incorrectas = ""
            for order in orders_incorrectas:
                str_incorrectas += "\t" + str(order.name) + "\n"
            raise ValidationError(
                _("¡Advertencia!, No se puede completar la operacion por que las siguientes ordenes no estan en estado pagado o publicado\n %s",
                  str_incorrectas))

        orders_refunded = self.pos_order_ids.filtered(lambda x: x.is_refunded or x.refunded_orders_count > 0)
        if len(orders_refunded) > 0:
            str_incorrectas = ""
            for order in orders_refunded:
                str_incorrectas += "\t" + str(order.name) + "\n"
            raise ValidationError(
                _("¡Advertencia!, No se puede completar la operacion por que las siguientes ordenes han sido reembolsadas\n %s",
                  str_incorrectas))

        orders_zero = self.pos_order_ids.filtered(lambda x: x.amount_total <= 0)
        if len(orders_zero) > 0:
            str_incorrectas = ""
            for order in orders_zero:
                str_incorrectas += "\t" + str(order.name) + "\n"
            raise ValidationError(
                _("¡Advertencia!, No se puede completar la operacion por que las siguientes ordenes son menores o igual a 0\n %s",
                  str_incorrectas))

        data_create = {
            'move_type': "out_invoice",
            'invoice_date': self.fecha_factura,
            'invoice_date_due': self.fecha_factura,
            'partner_id': self.partner_id.id,
            'l10n_mx_edi_payment_method_id': self.l10n_mx_edi_payment_method_id.id,
            'l10n_mx_edi_payment_policy': "PUE",
            'l10n_mx_edi_usage': "S01",
            'journal_id': self.journal_id.id,
            'tickets_global_ids': [(6, 0, [l.id for l in self.pos_order_ids])],
            'is_global_invoice': True,
            'periodicidad': self.periodicidad,
            "meses": self.meses,
            "year": self.year,

        }
        data_lines = self.get_invoice_lines_from_pos_orders()

        data_create['invoice_line_ids'] = data_lines
        _log.info("## Data Create %s", data_create)
        inv = self.env['account.move'].sudo().create(data_create)
        _log.info("Factura Global %s", inv)
        if inv:

            _log.info("TICKETS GLOBAL %s",inv.tickets_global_ids)
            inv.tickets_global_ids = [(6, 0, [l.id for l in self.pos_order_ids])]
            _log.info("TICKETS GLOBAL 2 %s", inv.tickets_global_ids)
            inv.l10n_mx_edi_payment_policy = "PUE"
            inv.action_post()
            for order in self.pos_order_ids:
                order.sudo().write({'state': "invoiced", "account_move": inv.id})
        action = {
            'name': _("Facturas Globales"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'target': 'current',
            'res_id':inv.id,
            'view_mode':'form',
            'views': [(self.env.ref('account.view_move_form').id, 'form')]


        }

        return action








