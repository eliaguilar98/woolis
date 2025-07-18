import logging
import decimal
from collections import defaultdict

from odoo import _, api, Command, fields, models
from lxml import etree
import logging
_logger = logging.getLogger(__name__)

class CompanySettingsInherit(models.Model):
    _inherit = 'res.company'

    product_inv_global_id = fields.Many2one("product.product", string="Producto Factura Global", default=lambda self: self.env['product.product'].search([('name','ilike','Venta')],limit=1).id )
    partner_inv_global_id = fields.Many2one("res.partner", string="Cliente Factura Global", default=lambda self: self.env['res.partner'].search([('name','ilike','PUBLICO EN GENERAL')],limit=1).id )
    journal_inv_global_id = fields.Many2one("account.journal", string="Diario Factura Global")


class ResConfigSettingsInherit(models.TransientModel):
    _inherit = 'res.config.settings'

    product_inv_global_id = fields.Many2one("product.product", string="Producto Factura Global", related='company_id.product_inv_global_id', readonly=False)
    partner_inv_global_id = fields.Many2one("res.partner", string="Cliente Factura Global", related='company_id.partner_inv_global_id', readonly=False)
    journal_inv_global_id = fields.Many2one("account.journal", string="Diario Factura Global", related='company_id.journal_inv_global_id', readonly=False)



