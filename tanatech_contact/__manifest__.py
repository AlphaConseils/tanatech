# -*- coding: utf-8 -*-
{
    "name": "Tanatech Contact",
    "version": "18.0.1.0.0",
    "author": "Nexources",
    "website": "https://www.nexources.com/",
    "category": "Contacts",
    "depends": ["base", "tanatech_base", "crm"],
    "data": [
        "data/ir_sequence_data.xml",
        "views/res_partner_views.xml",
        "views/crm_lead_views.xml",
        "views/res_company.xml"
    ],
    # "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
