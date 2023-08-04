# -*- coding: utf-8 -*-

import base64
import logging
import ssl
import subprocess
import tempfile
from datetime import datetime
from lxml import etree, objectify

_logger = logging.getLogger(__name__)

try:
    from OpenSSL import crypto
except ImportError:
    _logger.warning('OpenSSL library not found. If you plan to use l10n_mx_edi, please install the library from https://pypi.python.org/pypi/pyOpenSSL')

from pytz import timezone

from odoo import _, api, fields, models, tools
from odoo.exceptions import ValidationError, UserError
from odoo.tools.misc import DEFAULT_SERVER_DATETIME_FORMAT


KEY_TO_PEM_CMD = 'openssl pkcs8 -in %s -inform der -outform pem -out %s -passin file:%s'

class AccountInvoice(models.Model):
    _inherit = "account.move"


    def unlink(self):
        mx_edi = self.env.ref('cfdi4_enterprise.edi_cfdi_4_0')
        if self.env['account.edi.document'].sudo().search([
            ('edi_format_id', '=', mx_edi.id),
            ('attachment_id', '!=', False),
        ], limit=1):
            raise UserError(_(
                'You cannot remove a certificate if at least an invoice has been signed. '
                'Expired Certificates will not be used as Odoo uses the latest valid certificate. '
                'To not use it, you can unlink it from the current company certificates.'))
        res = super(Certificate, self).unlink()
        return res