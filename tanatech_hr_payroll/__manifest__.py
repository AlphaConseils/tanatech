# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Payroll",
    "version": "1.2.6",
    "summary": "Manage your Payroll activities",
    "description": "",
    "website": "https://www.nexources.com/",
    "depends": [
        "hr_payroll", 
        "tanatech_hr_contract", 
        "hr_attendance", 
        "mail", 
        "resource", 
        "hr_work_entry",
        "hr_holidays_attendance",
    ],
    "category": "Human Resources/Payroll",
    "data": [
        "data/hr_work_entry_data.xml",
        "data/hr_attendance_overtime_type_data.xml",
        "data/ir_actions_server.xml",
        "report/final_settlement.xml",

        # views
        "views/hr_employee_view.xml",
        "views/report_payslip_templates.xml",
        "views/report_payslip_nd_templates.xml",
        "views/hr_payslip_view.xml",
        "views/hr_work_entry_views.xml",
        "views/hr_attendance_view.xml",
        "security/ir.model.access.csv",
        "views/hr_attendance_overtime_menu.xml",
        "views/hr_attendance_overtime_resource_calendar_time.xml",
        "views/hr_attendance_overtime_resource_calendar.xml",
        "views/hr_attendance_overtime_with_datetimes_view.xml",
        "security/ir_rules.xml",
        "views/hr_attendance_overtime_type.xml",
        "views/res_config_settings_views.xml",
        "views/hr_leave_type_view.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
