# -*- coding: utf-8 -*-
{
    "name": "TANATECH - Sanction",
    "version": "1.2",
    "description": "Handle disciplinary sanction for employees",
    "summary": "Module for centralizing of disciplinary sanction",
    "author": "Nexources (Nadjim Attoumani)",
    "sequence": 177,
    "license": "LGPL-3",
    "category": "Human Resources/Sanction",
    "website": "https://www.nexources.com",
    "depends": ["approvals", "hr", "hr_payroll", "hr_holidays", "tanatech_base"],
    "data": [
        "security/sanction_security_group.xml",
        "security/ir.model.access.csv",
        # DATA
        "data/sanction_type_data.xml",
        "data/approval_category_data.xml",
        "data/sanction_demex_template.xml",
        "data/warning_notification_email_template.xml",
        "data/reference_data.xml",
        "data/lay_of_email_template.xml",
        "data/epl_mail_template.xml",
        # REPORT
        "report/ir_actions_report.xml",
        "report/demex_report.xml",
        "report/warning_report.xml",
        "report/lay_off_report.xml",
        "report/epl_report.xml",
        # VIEWS
        "views/sanction_sanction_menu.xml",
        "views/sanction_sanction_views.xml",
        "views/sanction_type_views.xml",
        "views/hr_employee_view.xml",
        "views/hr_employee_public.xml",
        "views/approval_request_from_inherit.xml",
        "views/res_user_form_view.xml",
        # "views/hr_payslip_view.xml",
        # "views/hr_payslip_input_type_view.xml",
        "views/hr_leave_type_view.xml",
        # WIZARD
        "wizard/sanction_type.xml",
        "wizard/mail_compose_message_form_inherit.xml",
        #
        "data/hr_leave_type_data.xml",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
    "assets": {
        "web.assets_backend": [
            "tanatech_sanction/static/src/**/*.js",
            "tanatech_sanction/static/src/js/*.js",
            "tanatech_sanction/static/src/**/*.scss",
            "tanatech_sanction/static/src/**/*.xml",
        ],
    },
}
