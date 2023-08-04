# -*- coding: utf-8 -*-
{
    'name': "Factura CFDI4 Pagos 2.0 Enterprise",

    'summary': """
	Factura CFDI4 Pagos 2.0 Enterprise
""",

    'description': """
	Modulo de Facturación electrónica para Odoo Enterprise 
    """,

    'author': "Xmarts",
    'website': "http://www.xmarts.com",
    'images': ['static/description/banners/banner.png'],
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/14.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'version': '0.1',
    #'live_test_url': "https://youtu.be/CNmOTkOoyMA",
    'category': 'Location',
    'version': '15.0.1',
    'price': 149,
    'currency': 'USD',
    'license': 'OPL-1',
    'depends': ['l10n_mx_edi','account'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner.xml',
        'views/account_payment.xml',
        'views/account_tax.xml',
        'views/account_move.xml',
        'views/res_config_view.xml',
        'data/ir_cron.xml',
        'data/4.0/cfdi.xml',
        'data/4.0/payment20.xml',
        'data/account_edi_data.xml',
        'report/report_invoice_cfdi.xml',
    ],
    'installable': True,
    'auto_install': False,
}
