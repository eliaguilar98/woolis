import logging
import decimal
from collections import defaultdict

from odoo import _, api, Command, fields, models
from lxml import etree
import logging
import datetime
_logger = logging.getLogger(__name__)

class PosOrderInherit(models.Model):
    _inherit = 'pos.order'

    payment_method_id = fields.Many2one("pos.payment.method",string="Metodo de pago", readonly=False,
                                            compute="_compute_payment_method", store=True)

    reverse_move = fields.Many2one('account.move', string='Reverse Move', readonly=True, copy=False)

    is_refund_order = fields.Boolean("Es una orden de reembolso o rembolsada?",compute="_compute_refund_related_fields",store=True,readonly=False)

    @api.depends('lines.refund_orderline_ids', 'lines.refunded_orderline_id','is_refund_order')
    def _compute_refund_related_fields(self):
        for order in self:
            order.refund_orders_count = len(order.mapped('lines.refund_orderline_ids.order_id'))
            order.is_refunded = order.refund_orders_count > 0
            order.refunded_order_ids = order.mapped('lines.refunded_orderline_id.order_id')
            order.refunded_orders_count = len(order.refunded_order_ids)
            if order.is_refunded or order.refunded_orders_count>0:
                order.is_refund_order = True
            else:
                order.is_refund_order = False

    @api.depends('payment_method_id','payment_ids')
    def _compute_payment_method(self):
        for rec in self:
            if rec.payment_ids:
                payments = list(rec.payment_ids)
                list(payments).sort(key=lambda x: x.amount, reverse=True)
                rec.payment_method_id = payments[0].payment_method_id.id
