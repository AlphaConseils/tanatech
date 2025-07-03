# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Contracts",
    "version": "1.1",
    "summary": "Manage your Contracts activities",
    "description": "",
    "website": "https://www.nexources.com/",
    "depends": ["hr_contract", "tanatech_base"],
    "category": "Human Resources/Contracts",
    "data": [
        # views
        'views/hr_contract_views.xml',
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
