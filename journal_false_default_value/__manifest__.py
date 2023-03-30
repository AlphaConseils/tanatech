# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Journal False Default Value',
    'version': '1.2',
    'summary': 'Sales internal machinery',
    'description': """
This module remove journal_id default value on account.
    """,
    'depends': ['account_accountant', 'sale'],
    'data': [
        'views/account_move_views.xml'
    ],
    'installable': True,
    'auto_install': False,
}