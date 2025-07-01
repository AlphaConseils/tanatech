# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name' : 'Journal user restrict',
    'version' : '1.1',
    'summary': 'Restrict journal access for certain users',
    'sequence': 10,
    'category': 'Accounting/Accounting',
    'website': 'https://www.nexources.com',
    'depends' : ['account'],
    'data': [
        'security/ir_rule.xml',

        'views/account_journal_views.xml'
    ],
    'license': 'LGPL-3',
}
