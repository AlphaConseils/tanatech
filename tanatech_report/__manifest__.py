# -*- coding: utf-8 -*-
{
    'name': "tanatech_report",

    'summary': """
        change font color in the document""",

    'description': """
        change font color in the document
    """,

    'author': "Nexources",
    'website': "http://www.nexources.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base','account', 'sale', 'purchase', 'stock','sale_management','tanatech_account','hr_expense'],

    # always loaded
    'data': [
        'report/font_sale_report.xml',
        'report/font_purchase_report.xml',
        'report/font_purchaseorder_report.xml',
        'report/font_stockpicking_report.xml',
        'report/font_sale_managment.xml',
        'report/font_report_delivery_document.xml',
        'report/font_report_account_document.xml',
        'report/font_report_hr_expense.xml',
        'report/font_payement.xml',
        'report/account_report_invoice_document_copy_2.xml'
    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
    'assets':{
        'web.report_assets_pdf':[
            'tanatech_report/static/report.scss'
        ]
    }
}
