import logging
import decimal
from collections import defaultdict

from odoo import _, api, Command, fields, models
from odoo.exceptions import ValidationError, UserError
from lxml import etree
import logging
import datetime
_logger = logging.getLogger(__name__)

class AccountMoveLineInherit(models.Model):
    _inherit = 'account.move.line'

    pos_order_id = fields.Many2one("pos.order",string="Orden del pos relacionada")
    pos_order_tax_json = fields.Char(string="String desglozado impuestos pos order" ,store=True,
                                             compute='compute_json_tax_pos_order')

    @api.depends('pos_order_tax_json', "pos_order_id")
    def compute_json_tax_pos_order(self):
        for rec in self:
            if rec.pos_order_id:
                taxs_ids = rec.pos_order_id.lines.filtered(lambda x: len(x.tax_ids)>0).mapped('tax_ids')

                rec.pos_order_tax_json = ''
                for tax in taxs_ids:
                    total_base = sum([line.price_subtotal for line in rec.pos_order_id.lines.filtered(lambda x: tax in x.tax_ids)])
                    total_impuestos = sum([line.price_subtotal_incl - line.price_subtotal for line in rec.pos_order_id.lines.filtered(lambda x: tax in x.tax_ids)])
                    rec.pos_order_tax_json += ", Impuesto "+str(tax.name)+" : Base "+str(round(total_base,2))+": Total impuesto "+str(round(total_impuestos,2))
            else:
                rec.pos_order_tax_json=''


    @api.onchange("pos_order_id")
    def _onchange_json_tax_pos_order(self):
        self.compute_json_tax_pos_order()



class AccountMoveInherit(models.Model):
    _inherit = 'account.move'

    is_global_invoice = fields.Boolean(string="Es una factura global", default=False)
    tickets_global_ids = fields.Many2many("pos.order", string="Tickets relacionados")
    periodicidad = fields.Selection([
        ('01', 'Diaria'),
    ], 'Periodicidad',
        default='01')
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
    ], 'Mes')
    year = fields.Integer('Año')

    def button_cancel_posted_moves(self):
        res = super(AccountMoveInherit, self).button_cancel_posted_moves()
        for rec in self:
            if rec.tickets_global_ids:
                for ticket in rec.tickets_global_ids:
                    ticket.state = 'done'
                    ticket.account_move = False
        return res

    def button_draft(self):
        res = super(AccountMoveInherit, self).button_draft()
        for rec in self:
            if rec.tickets_global_ids:
                for ticket in rec.tickets_global_ids:
                    ticket.state = 'done'
                    ticket.account_move = False
        return res

    def action_post(self):
        res = super(AccountMoveInherit, self).action_post()
        for rec in self:
            if rec.tickets_global_ids:
                for ticket in rec.tickets_global_ids:
                    if ticket.state == 'invoiced' and ticket.account_move and ticket.account_move.id != rec.id:
                        raise ValidationError(_("¡Advertencia!, No se puede completar la operacion por que el ticket ya esta incluido en otra factura\n\t- Ticket: %s \n\t- Factura: %s",ticket.name,ticket.account_move.name))
                    ticket.state = 'invoiced'
                    ticket.account_move = rec.id
        return res

    def button_abandon_cancel_posted_posted_moves(self):
        res = super(AccountMoveInherit, self).button_abandon_cancel_posted_posted_moves()
        for rec in self:
            if rec.tickets_global_ids:
                for ticket in rec.tickets_global_ids:
                    if ticket.state == 'invoiced' and ticket.account_move and ticket.account_move.id != rec.id:
                        raise ValidationError(_("¡Advertencia!, No se puede completar la operacion por que el ticket ya esta incluido en otra factura\n\t- Ticket: %s \n\t- Factura: %s",ticket.name,ticket.account_move.name))
                    ticket.state = 'invoiced'
                    ticket.account_move = rec.id
        return res

