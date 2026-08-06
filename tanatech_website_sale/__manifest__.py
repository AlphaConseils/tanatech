# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Website Sale",
    "version": "1.1.2",
    "summary": "Follow-up activities upon website order confirmation",
    "description": """
When a customer confirms their order on the website (eCommerce payment or
quotation signature on the portal), follow-up activities are created for:
- the sales team, on the quotation;
- the procurement team, on the delivery order(s);
- the finance team, on the invoice (as soon as it is created).

The recipient teams are configured in Website > Configuration > Settings.
    """,
    "website": "https://www.nexources.com/",
    "category": "Website/Website",
    "sequence": 999,
    "depends": ["website_sale", "sale_stock"],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
    "license": "LGPL-3",
}
