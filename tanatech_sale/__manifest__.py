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
        'tanatech_base'
    ],
    'description': "",
    'data': [
        # data

        # security
        'security/res_groups.xml',

        # views
        'views/sale_order_views.xml',

        # report
        'report/sale_report.xml',
        'report/inherit_report_saleorder_document.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}