# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Tanatech Sale',
    'version': '1.2',
    'website': 'https://www.nexources.com/',
    'category': 'Services/Project',
    'sequence': 999,
    'depends': [
        'sale',
    ],
    'description': "",
    'data': [
        # data

        # security
        'security/res_groups.xml',

        # views
        'views/sale_order_views.xml'
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}