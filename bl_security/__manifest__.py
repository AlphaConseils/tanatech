# -*- coding: utf-8 -*-
{
    'name': "bl_security",

    'summary': """
       restrict users to stock.move
       """,

    'description': """
        restrict users to add line in stock picking where the article Bl in users views is checked
    """,

    'author': "Nexources",
    'website': "http://www.nexources.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','stock'],

    # always loaded
    'data': [
        'views/res_users_inherit_views.xml',
        # 'views/stock_pickng_inherit_views.xml',
    ],
}
