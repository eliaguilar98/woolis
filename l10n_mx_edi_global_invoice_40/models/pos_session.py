import logging
import decimal
from collections import defaultdict
from itertools import groupby
from operator import itemgetter
from odoo import _, api, Command, fields, models
from lxml import etree
import logging
import datetime
_logger = logging.getLogger(__name__)

class PosSessionInherit(models.Model):
    _inherit = 'pos.session'

    make_global_invs = fields.Boolean("Realizar factura global al cierre?",default=False)

    @api.model
    def set_option_global_inv_active(self,session_id,do_global_inv):
        session = self.browse(session_id)
        if session:
            session.make_global_invs = do_global_inv
            return 1
        return 0

    def _compute_metodo_pago_id(self, orders):
        for wizard in self:
            forma_pago = {}
            for line in orders:
                for l in line.payment_ids:
                    if l.payment_method_id in forma_pago:
                        forma_pago[l.payment_method_id] += l.amount
                    else:
                        forma_pago[l.payment_method_id] = l.amount
            if forma_pago:
                l10n_mx_edi_payment_method_id = max(forma_pago.items(), key=lambda x: x[1])[0]
                return l10n_mx_edi_payment_method_id.l10n_mx_edi_payment_method_id.id or False
        return False


    def get_invoice_lines_from_pos_orders(self,orders):
        pos_config = self.config_id


        pre_invoice_line_ids = []

        for order in orders:
            pre_invoice_line_ids += order._prepare_invoice_line_global(order.pos_reference)



        product_uom_activity = pos_config.product_global_id.uom_id
        product_product_sell = pos_config.product_global_id

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

    def make_invoice_global_with_uninvoiced_orders(self):
        orders = self.env['pos.order'].search([('session_id', '=', self.id), ('state', '=', 'paid')])
        orders_refunded = orders.filtered(lambda x: x.is_refunded or x.refunded_orders_count > 0 or x.amount_paid <0)
        orders = orders - orders_refunded
        pos_config =self.config_id
        if pos_config and pos_config.product_global_id and pos_config.partner_global_id and pos_config.journal_global_id and pos_config.active_facturacion_global:
            data_create = {
                'move_type': "out_invoice",
                'partner_id': pos_config.partner_global_id.id,
                'l10n_mx_edi_payment_method_id': self._compute_metodo_pago_id(orders),
                'l10n_mx_edi_payment_policy': "PUE",
                'l10n_mx_edi_usage': "S01",
                'journal_id': pos_config.journal_global_id.id,
                'tickets_global_ids': [(6, 0, [l.id for l in orders])],
                'is_global_invoice': True,
                'periodicidad': '01',
                "meses": datetime.datetime.now().strftime("%m"),
                "year": int(datetime.datetime.now().strftime("%Y")),

            }
            data_lines = self.get_invoice_lines_from_pos_orders(orders)

            data_create['invoice_line_ids'] = data_lines
            inv = self.env['account.move'].sudo().create(data_create)
            if inv:
                inv.tickets_global_ids = [(6, 0, [l.id for l in orders])]
                inv.l10n_mx_edi_payment_policy = "PUE"
                inv.action_post()
                for order in orders:
                    order.sudo().write({'state': "invoiced", "account_move": inv.id})


    def close_session_from_ui(self, bank_payment_method_diff_pairs=None):
        """Calling this method will try to close the session.

        param bank_payment_method_diff_pairs: list[(int, float)]
            Pairs of payment_method_id and diff_amount which will be used to post
            loss/profit when closing the session.

        If successful, it returns {'successful': True}
        Otherwise, it returns {'successful': False, 'message': str, 'redirect': bool}.
        'redirect' is a boolean used to know whether we redirect the user to the back end or not.
        When necessary, error (i.e. UserError, AccessError) is raised which should redirect the user to the back end.
        """
        ######
        if self.make_global_invs:
            self.make_invoice_global_with_uninvoiced_orders()
        #####
        return super(PosSessionInherit,self).close_session_from_ui(bank_payment_method_diff_pairs)
