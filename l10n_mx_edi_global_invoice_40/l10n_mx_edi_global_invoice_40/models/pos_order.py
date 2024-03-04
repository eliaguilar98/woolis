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

    @api.depends('payment_method_id','payment_ids')
    def _compute_payment_method(self):
        for rec in self:
            if rec.payment_ids:
                payments = list(rec.payment_ids)
                list(payments).sort(key=lambda x: x.amount, reverse=True)
                rec.payment_method_id = payments[0].payment_method_id.id
