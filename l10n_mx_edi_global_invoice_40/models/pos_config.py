import logging
import decimal
from collections import defaultdict

from odoo import _, api, Command, fields, models
from lxml import etree
import logging
import datetime
_logger = logging.getLogger(__name__)

class PosConfigInherit(models.Model):
    _inherit = 'pos.config'

    active_facturacion_global = fields.Boolean("Facturación global Activa")

    product_global_id = fields.Many2one("product.product", string="Producto Factura Global",
                                            default=lambda self: self.env['product.product'].search(
                                                [('name', 'ilike', 'Venta')], limit=1).id)
    partner_global_id = fields.Many2one("res.partner", string="Cliente Factura Global",
                                            default=lambda self: self.env['res.partner'].search(
                                                [('name', 'ilike', 'PUBLICO EN GENERAL')], limit=1).id)
    journal_global_id = fields.Many2one("account.journal", string="Diario Factura Global")




