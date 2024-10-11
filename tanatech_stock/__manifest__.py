# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Inventory",
    "version": "1.1",
    "summary": "Manage your stock and logistics activities",
    "description": "",
    "website": "https://www.nexources.com/",
    "depends": ["stock", "tanatech_base"],
    "category": "Inventory/Inventory",
    "sequence": 25,
    "data": [
        # report
        "report/stock_report_views.xml",
        "report/deliveryslip_dispatch.xml",
        "report/tanatech_report_delivery_document_a5.xml",
        "report/inherit_report_delivery_document.xml",
        # views
        "views/stock_picking_views.xml"
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
