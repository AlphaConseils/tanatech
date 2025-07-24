# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Payroll",
    "version": "1.1",
    "summary": "Manage your Payroll activities",
    "description": "",
    "website": "https://www.nexources.com/",
    "depends": ["hr_payroll", "tanatech_base", "hr_attendance", "mail", "resource", "hr_work_entry"],
    "category": "Human Resources/Payroll",
    "data": [
        "data/hr_work_entry_data.xml",
        # views
        # "views/report_payslip_templates.xml",
        "views/hr_attendance_overtime_view.xml",
        "views/hr_payslip_view.xml",
        "views/hr_work_entry_views.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
