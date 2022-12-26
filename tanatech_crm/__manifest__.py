# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Tanatech CRM',
    'version': '1.2',
    'website': 'https://www.nexources.com/',
    'sequence': 999,
    'depends': [
        'crm',
        'tanatech_sale'
    ],
    'description': "",
    'data': [
        # data

        # security

        # views
        'views/crm_lead_views.xml'
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}