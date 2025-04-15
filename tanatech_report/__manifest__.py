# -*- coding: utf-8 -*-
{
    "name": "tanatech_report",
    "summary": """
        change font color in the document""",
    "description": """
        change font color in the document
    """,
    "author": "Nexources",
    "website": "http://www.nexources.com",
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    "category": "Uncategorized",
    "version": "0.1",
    # any module necessary for this one to work correctly
    "depends": [
        "base",
        "account",
        "sale",
        "purchase",
        "stock",
        "sale_management",
        "tanatech_account",
        "hr_expense",
    ],
    # always loaded
    "data": [
        "report/report_delivery_note.xml",
    ],
    "assets": {
        "web.report_assets_common": [
            "tanatech_report/static/src/report.css",
        ]
    },
    "license": "LGPL-3",
}
