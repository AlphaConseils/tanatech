# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    def action_generate_opavie_report(self):
        return self.env.ref('opavie_excel_report.action_opavie_report').report_action(self)
