# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields, _
import logging


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    is_undeclared_payslip = fields.Boolean('Is undeclared payslip ?', compute="_define_payslip_nature", default=False, store=False)
    @api.depends('contract_id')
    def _define_payslip_nature(self):
        for payslip in self:
            payslip.is_undeclared_payslip = False
            if payslip.contract_id and payslip.contract_id.contract_category == 'not_declared':
                payslip.is_undeclared_payslip = True

    overtime_hours_count = fields.Float(compute='_compute_overtime_hours') 

    employee_id = fields.Many2one(
        'hr.employee', required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), '|', ('active', '=', True), ('active', '=', False)]")
    

    def _compute_contract_domain_ids(self):
        for payslip in self:
            payslip.contract_domain_ids = self.env['hr.contract'].search([
                ('company_id', '=', payslip.company_id.id),
                ('employee_id', '=', payslip.employee_id.id),
                ('state', 'in', ['open', 'open_not_declared', 'close']),
            ])

    def action_print_nd_payslip(self):
        return self.env.ref('tanatech_hr_payroll.action_report_nd_payslip').report_action(self)

    def action_open_overtime(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Overtime This Month'),
            'view_mode': 'list,form',
            'res_model': 'hr.attendance.overtime.with.datetimes',
            'domain': [('employee_id', '=', self.employee_id.id), ('date', '>=', self.date_from), ('date', '<=', self.date_to)],
            'context': "{'create': False}",
        }

    @api.depends('date_from', 'date_to', 'employee_id.overtime_with_datetimes_ids.duration', 'employee_id.attendance_ids')
    def _compute_overtime_hours(self):
        for payslip in self:
            mapped_validated_overtimes = dict(self.env['hr.attendance.overtime.with.datetimes']._read_group(
                domain=[('date', '>=', payslip.date_from), ('date', '<=', payslip.date_to)],
                groupby=['employee_id'],
                aggregates=['duration:sum']
            ))
            payslip.overtime_hours_count = mapped_validated_overtimes.get(payslip.employee_id, 0)



    def compute_sheet(self):
        for slip in self:
            slip.employee_id.generate_work_entries(
                slip.date_from,
                slip.date_to,
                force=True,
            )

        return super().compute_sheet()