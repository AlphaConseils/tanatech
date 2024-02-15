# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Product Pricelist Display',
    'version' : '1.0',
    'summary': 'Product pricelist',
    'sequence': 10,
    'description': """Display pricelist value in product list""",
    'category': '',
    'website': '',
    'images': [],
    'depends': ['sale'],
    'data': [
        'views/product_pricelist_views.xml',
        'views/product_template_views.xml',
    ],
    'demo': [
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'assets': {
        'web._assets_primary_variables': [

        ],
        'web.assets_backend': [
            'product_pricelist_display/static/src/js/basic_model.js',
            'product_pricelist_display/static/src/js/list_renderer.js',
        ],
        'web.assets_frontend': [

        ],
        'web.assets_tests': [

        ],
        'web.qunit_suite_tests': [

        ],
        'web.assets_qweb': [

        ],
    },
}
