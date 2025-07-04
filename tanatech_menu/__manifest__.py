# __manifest__.py
{
    "name": "Tanatech Menu",
    "summary": "menu personnaliser",
    "version": "1.0",
    "category": "Uncategorized",
    "author": "Nexources",
    "depends": ["point_of_sale"],
    "data": [
        # WIZARD
        "wizard/pos_report_wizard_views.xml",
        # VIEWS
        "views/menu.xml",
        # REPORT
        "report/report_saledetails_bis.xml",
        "report/ir_actions_report.xml",
        "report/report_saledetails.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "tanatech_menu/static/src/app/models/pos_order_line.js",
        ]
    },
    "installable": True,
    "application": True,
    "auto_install": True,
    "license": "LGPL-3",
}
