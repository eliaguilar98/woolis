# -*- coding: utf-8 -*-
from . import models
from . import wizard
from odoo import api, SUPERUSER_ID, _

def pre_init_check(cr):
    from odoo.service import common
    from odoo.exceptions import UserError
    version_info = common.exp_version()
    server_serie = version_info.get('server_serie')
    if '15.' not in server_serie:
        raise UserError(_('Este modulo esta diseñado para odoo 15.x, encontrado %s.') %
                        server_serie)
    return True