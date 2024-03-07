import logging
import decimal
from collections import defaultdict

from odoo import _, api, Command, fields, models
from lxml import etree
import logging
import datetime
_logger = logging.getLogger(__name__)
from odoo.tools import float_is_zero, float_round, float_repr, float_compare

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

    @api.model
    def _get_invoice_lines_values(self, line_values, pos_order_line):
        return {
            'product_id': line_values['product'].id,
            'quantity': line_values['quantity'],
            'discount': line_values['discount'],
            'price_unit': line_values['price_unit'],
            'name': line_values['name'],
            'tax_ids': [(6, 0, line_values['taxes'].ids)],
            'product_uom_id': line_values['uom'].id,
        }

    def _prepare_invoice_line_global(self,receipt_number=False):
        """ Prepare a list of orm commands containing the dictionaries to fill the
        'invoice_line_ids' field when creating an invoice.

        :return: A list of Command.create to fill 'invoice_line_ids' when calling account.move.create.
        """
        sign = 1 if self.amount_total >= 0 else -1
        line_values_list = self._prepare_tax_base_line_values(sign=sign)
        invoice_lines = []
        for line_values in line_values_list:
            line = line_values['record']
            invoice_lines_values = self._get_invoice_lines_values(line_values, line)
            if receipt_number:
                invoice_lines_values['name'] = receipt_number

            invoice_lines.append(invoice_lines_values)

        return invoice_lines
