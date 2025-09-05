# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields
import logging


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    overtime_hours_count = fields.Float(compute='_compute_overtime_hours') 
    total_overtime = fields.Float(related='employee_id.total_overtime')

    employee_id = fields.Many2one(
        'hr.employee', required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), '|', ('active', '=', True), ('active', '=', False)]")

    def action_open_overtime(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Overtime This Month',
            'view_mode': 'list,form',
            'res_model': 'hr.attendance.overtime',
            'domain': [('employee_id', '=', self.employee_id.id), ('state', '=', 'approved')],
            'context': "{'create': False}",
        }

    @api.depends('date_from', 'date_to', 'employee_id.overtime_ids.duration', 'employee_id.attendance_ids', 'employee_id.attendance_ids.overtime_status')
    def _compute_overtime_hours(self):
        for payslip in self:
            mapped_validated_overtimes = dict(self.env['hr.attendance.overtime']._read_group(
                domain=[('state', '=', 'approved'), ('adjustment', '=', False), ('date', '>=', payslip.date_from), ('date', '<=', payslip.date_to)],
                groupby=['employee_id'],
                aggregates=['duration:sum']
            ))

            mapped_overtime_adjustments = dict(self.env['hr.attendance.overtime']._read_group(
                domain=[('adjustment', '=', True), ('date', '>=', payslip.date_from), ('date', '<=', payslip.date_to)],
                groupby=['employee_id'],
                aggregates=['duration:sum']
            ))
            payslip.overtime_hours_count = mapped_validated_overtimes.get(payslip.employee_id, 0) + mapped_overtime_adjustments.get(payslip.employee_id, 0)
            import logging
            logging.info('DONE')