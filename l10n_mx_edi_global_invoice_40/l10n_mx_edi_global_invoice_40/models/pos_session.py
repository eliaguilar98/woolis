import logging
import decimal
from collections import defaultdict

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

    def _compute_metodo_pago_id(self,orders):
        l10n_mx_edi_payment_method_id = False
        for wizard in self:
            forma_pago = {}
            for line in orders:
                for l in line.payment_ids:
                    if l.payment_method_id.id in forma_pago:
                        forma_pago[l.payment_method_id.id] += l.amount
                    else:
                        forma_pago[l.payment_method_id.id] = l.amount
            forma_pago_sort = sorted(forma_pago, reverse=True)
            l10n_mx_edi_payment_method_id = forma_pago_sort[0]
            if l10n_mx_edi_payment_method_id:
                return l10n_mx_edi_payment_method_id
            return False

    def make_invoice_global_with_uninvoiced_orders(self):
        orders = self.env['pos.order'].search([('session_id', '=', self.id), ('state', '=', 'paid')])
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
            data_lines = []
            for line in orders:
                lines_impuestos = line.lines.filtered(lambda x: x.tax_ids)
                impuestos = []
                impuesto_0 = self.env['account.tax'].search([('type_tax_use', '=', 'sale'), ('amount', '=', 0)],
                                                            limit=1)
                lines_groups_tax = {}
                for linea_pos in line.lines:
                    if linea_pos.tax_ids:
                        if linea_pos.tax_ids[0].id in lines_groups_tax:
                            lines_groups_tax[linea_pos.tax_ids[0].id].append(linea_pos)
                        else:
                            lines_groups_tax[linea_pos.tax_ids[0].id] = [linea_pos]
                    else:
                        if impuesto_0.id in lines_groups_tax:
                            lines_groups_tax[impuesto_0.id].append(linea_pos)
                        else:
                            lines_groups_tax[impuesto_0.id] = [linea_pos]

                for key in lines_groups_tax.keys():
                    amount_total = sum([line_pos.price_subtotal for line_pos in lines_groups_tax[key]])
                    data = {
                        'product_id': pos_config.product_global_id.id,
                        'name': line.name,
                        'quantity': 1,
                        'price_unit': amount_total,
                        'tax_ids': [(6, 0, [key])],
                        'pos_order_id': line.id,
                    }

                    data_lines.append((0, 0, data))

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
