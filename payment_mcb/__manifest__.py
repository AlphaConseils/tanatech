# -*- coding: utf-8 -*-
{
    "name": "MCB Payment Gateway - Hosted Session",
    "version": "18.0.1.2.0",
    "category": "Accounting/Payment Providers",
    "summary": "MCB Payment Gateway integration via Hosted Session",
    "description": """
        Odoo 18 payment module using MCB Payment Gateway (Mauritius Commercial Bank)
        in Hosted Session mode. Card data is collected directly
        in iFrames hosted by MCB — outside the scope of PCI DSS.
    """,
    "depends": ["payment", "website_sale"],
    "data": [
        "security/ir.model.access.csv",
        "data/payment_provider_data.xml",
        "views/payment_mcb_templates.xml",
        "views/payment_provider_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_mcb/static/src/css/payment_mcb.css",
            "payment_mcb/static/src/js/payment_mcb_form.js",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
    "license": "LGPL-3",
}
