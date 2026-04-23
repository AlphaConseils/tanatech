# -*- coding: utf-8 -*-
{
    "name": "payment_mvola",
    "summary": "ecommerce mvola payment",
    "author": "My Company",
    "website": "https://www.yourcompany.com",
    "category": "Hidden",
    "version": "18.0.1.1.0",
    "depends": ["payment", "website_sale"],
    "data": [
        # templates first (referenced by data files below)
        "views/payment_mvola_templates.xml",
        "views/payment_provider_views.xml",
        # data
        "data/payment_method_data.xml",
        "data/payment_provider_data.xml",
        "data/cron.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_mvola/static/src/js/payment_form.js",
            "payment_mvola/static/src/scss/payment_form.scss",
        ],
    },
    "license": "LGPL-3",
}
