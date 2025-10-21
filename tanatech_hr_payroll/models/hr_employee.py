# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields
import logging

from datetime import datetime
import calendar


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    classification = fields.Char(string='Classification')
    indice = fields.Char(string='Indice')

    overtime_with_datetimes_ids = fields.One2many('hr.attendance.overtime.with.datetimes', 'employee_id')

    overtime_with_datatimes_hours_count = fields.Float(compute='_compute_overtime_with_datatimes_hours', compute_sudo=True)

    @api.depends('overtime_with_datetimes_ids.duration', 'attendance_ids')
    def _compute_overtime_with_datatimes_hours(self):
        for employee in self:
            # Current date
            today = datetime.today()
            # First day of the current month
            first_day = today.replace(day=1)
            # Last day of the current month
            last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])
            mapped_overtimes = dict(self.env['hr.attendance.overtime.with.datetimes']._read_group(
                domain=[('date', '>=', first_day.date()), ('date', '<=', last_day.date())],
                groupby=['employee_id'],
                aggregates=['duration:sum']
            ))
            employee.overtime_with_datatimes_hours_count = mapped_overtimes.get(employee, 0)

    def action_open_overtime_with_datatimes(self):
        self.ensure_one()
        # Current date
        today = datetime.today()
        # First day of the current month
        first_day = today.replace(day=1)
        # Last day of the current month
        last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])
        return {
            'type': 'ir.actions.act_window',
            'name': 'Overtime This Month',
            'view_mode': 'list,form',
            'res_model': 'hr.attendance.overtime.with.datetimes',
            'domain': [('employee_id', '=', self.id), ('date', '>=', first_day.date()), ('date', '<=', last_day.date())],
            'context': "{'create': False}",
        }