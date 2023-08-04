# -*- coding: utf-8 -*-

from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import ValidationError, UserError, except_orm
from odoo import _, api, fields, models, tools
from pytz import timezone
import base64
import logging
import ssl
import subprocess
import tempfile
from datetime import datetime
from hashlib import sha1

_logger = logging.getLogger(__name__)

try:
    from OpenSSL import crypto
except ImportError:
    _logger.warning(
        'OpenSSL library not found. If you plan to use l10n_mx_edi, please install the library from https://pypi.python.org/pypi/pyOpenSSL')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'


    edi_user_bd = fields.Char(
        string = "Usuario BD",
        related="company_id.edi_user_bd",
        readonly=False,
        )
    edi_passw_bd = fields.Char(
        string = "Contraseña BD",
        related="company_id.edi_passw_bd",
        readonly=False
        )
    edi_url_bd = fields.Char(
        string = "URL BD",
        related="company_id.edi_url_bd",
        readonly=False
        )
    edi_name_bd = fields.Char(
        string = "Nombre BD",
        related="company_id.edi_name_bd",
        readonly=False
        )

    edi_user_pac = fields.Char(
        string="Usuario para PAC.",
        related="company_id.edi_user_pac",
        readonly=False
    )
    edi_pass_pac = fields.Char(
        string="Contraseña para PAC.",
        related="company_id.edi_pass_pac",
        readonly=False    
    )