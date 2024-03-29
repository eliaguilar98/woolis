# -*- coding: utf-8 -*-
{
    'name': 'Factura Global CFDI 4.0',
    'version': '17.0.0.0.2',
    'category': 'Tools',
    'author': 'INFLEXYON',
    'website': '',
    'license': 'LGPL-3',
    'summary': 'Generacion de facturas globales apartir de las ordenes del POS',
    'description': """Generacion de facturas globales apartir de las ordenes del POS""",

    'depends': [
        'point_of_sale',
        'account',
        'l10n_mx_edi',
    ],
    "data": [
        'data/data_global_invoice.xml',
        'security/ir.model.access.csv',
        'wizard/pos_order_make_invoice_view.xml',
        'wizard/res_config_settings.xml',
        'views/account_move_views.xml',
        'report/cfdi_report_inherit.xml',
        'views/pos_order_views.xml',
        'views/pos_config_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'l10n_mx_edi_global_invoice_40/static/src/**/*',
        ]
    },
    'images': [
        'static/description/banner.jpg',
    ],
    'demo': [],
    'external_dependencies': {
    },
    'application': True,
    'installable': True,
    'auto_install': False,
    'website': 'https://www.inflexyon.mx',
    'pre_init_hook': 'pre_init_check',
}
