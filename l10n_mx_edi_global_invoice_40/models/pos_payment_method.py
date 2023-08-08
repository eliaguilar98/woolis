# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from dateutil.relativedelta import relativedelta
from datetime import datetime
import logging
_log = logging.getLogger("___name: %s" % __name__)


class PaymentMethodPos(models.Model):
    _inherit = "pos.payment.method"

    payment_method_c = fields.Many2one('l10n_mx_edi.payment.method', string="Forma de pago")
