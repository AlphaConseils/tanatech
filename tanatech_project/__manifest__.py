# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Project",
    "version": "1.2",
    "website": "https://www.nexources.com/",
    "category": "Services/Project",
    "sequence": 999,
    "summary": "Organize and plan Tanatech's projects",
    "depends": ["project", "sale_project", "industry_fsm"],
    "description": "",
    "data": [
        # data
        # 'data/translation.xml',
        "views/project_views.xml",
        "data/security.xml",
        "views/project_task_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
    "license": "LGPL-3",
}
