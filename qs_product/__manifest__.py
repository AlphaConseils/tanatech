# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'QS Product',
    'version': '1.2',
    'category': 'Product/Products',
    'summary': 'Product internal machinery',
    'description': """
    Long description of module's product
    """,
    'depends': ['product'],
    'data': [
        'report/book_rent_report.xml',
        'report/book_rent_templates.xml',
        'views/product_pricelist_views.xml',
        'views/product_template_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
