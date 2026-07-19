# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Contracts",
    "version": "1.4",
    "summary": "Manage your Contracts activities",
    "description": "",
    "website": "https://www.nexources.com/",
    "depends": ["hr", "hr_contract", "hr_payroll", "tanatech_base"],
    "category": "Human Resources/Contracts",
    "data": [
        # security
        'security/ir.model.access.csv',
        'security/res_groups.xml',
        # data
        'data/ir_actions_server_data.xml',
        # views
        'views/hr_contract_views.xml',
        'views/hr_payslip_view.xml',
        'views/hr_payroll_menu.xml',
        'views/hr_payroll_report_views.xml',
        'views/hr_payroll_structure_type_views.xml',
        'views/hr_payroll_structure_views.xml',
        'views/hr_salary_attachment_views.xml',
        # wizard
        'wizard/hr_payroll_index_wizard_views.xml',
    ],
    "assets": {
        "web.assets_backend": [
            "tanatech_hr_contract/static/src/js/*.js",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
