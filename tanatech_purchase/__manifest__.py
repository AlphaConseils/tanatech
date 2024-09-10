# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Tanatech Purchase',
    'version': '1.2',
    'website': 'https://www.nexources.com/',
    'category': 'Services/Project',
    'sequence': 999,
    'depends': [
        'base',
        'purchase',
    ],
    'description': "",
    'data': [
        # data

        # security
        'security/purchase_security.xml',

        # views
 
        # report
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}