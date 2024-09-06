# -*- coding: utf-8 -*-
{
    'name': "TANATECH - Sale report NA",

    'summary': "TANATECH - Sale report NA",

    'author': "Nexources",
    'website': "http://www.nexources.com",

    'category': 'Uncategorized',
    'version': '0.1',

    'depends': ['base', 'tanatech_base', 'sale'],

    'data': [
        'report/parperformat_a4.xml',
        'report/custom_external_layout.xml',
        'report/report_sale_NA.xml',
        'report/inherit_external_layout_striped.xml',
        'views/sale_order.xml',
    ],
}
