# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Holidays",
    "version": "1.0",
    "summary": "Manage your Holidays activities",
    "description": "",
    "website": "https://www.nexources.com/",
    "depends": ["hr_holidays", "tanatech_base"],
    "category": "Human Resources/Holidays",
    "data": [
        "views/hr_leave_type_views.xml",
        "views/hr_leave_views.xml",
        "data/hr_leave_type_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
