# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Tanatech CRM',
    'version': '1.2',
    'website': 'https://www.nexources.com/',
    'sequence': 999,
    'depends': [
        'sale_crm',
        'tanatech_sale'
    ],
    'description': "",
    'data': [
        # data

        # security
        'security/crm_security.xml',

        # views
        'views/crm_lead_views.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}