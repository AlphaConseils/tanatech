# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, time, date, timedelta
from pytz import timezone, utc

from random import randint

from odoo import models, fields, api

import pytz

class HrAttendanceOvertimeWithDatetimes(models.Model):
    _name = "hr.attendance.overtime.with.datetimes"
    _description = "Attendance Overtime With start and end date"
    _rec_name = 'employee_id'
    _order = 'start_date desc'

    employee_id = fields.Many2one(
        'hr.employee', string="Employee",
        required=True, ondelete='cascade', index=True, store=True)

    company_id = fields.Many2one(related='employee_id.company_id', store=True)

    attendance_id = fields.Many2one('hr.attendance', string="Attendance", index=True, store=True)

    date = fields.Date(string='Day', compute='_get_date', store=True)
    start_date = fields.Datetime(string='Start Date', required=True, store=True)
    end_date = fields.Datetime(string='End Date', required=True, store=True)
    duration = fields.Float(string='Duration', compute='_compute_duration', default=0.0, store=True)

    overtime_type = fields.Selection(
        selection=[
            ('day_work_on_regular_day', "Day work on regular day"),
            ('casual_night_work_on_regular_day', "Casual night work on regular day"),
            ('occasional_night_work_on_weekends', "Occasional night work on weekend"),
            ('day_work_on_sunday', "Day work on Sunday"),
            ('night_work_on_sunday', "Night work on Sunday"),
            ('work_on_public_holidays', "Hours Worked On Public Holidays"),
        ],
        string="Overtime Type",
        readonly=True,
        default='day_work_on_regular_day'
    )

    overtime_type_ids = fields.Many2many(
        'hr.attendance.overtime.type', 
        'hr_attendance_overtime_type_rel',
        string='Overtime Type',
        compute='_get_overtime_type'
    )

    overtime_threshold = fields.Integer(
        string="Tolerance Time In Favor Of Company", 
        related='company_id.overtime_threshold', 
        readonly=False
    )

    @api.depends('overtime_type')
    def _get_overtime_type(self):
        for record in self:
            overtime_type_id = self.env['hr.attendance.overtime.type'].search([('strategic_name', '=', record.overtime_type)], limit=1)
            record.overtime_type_ids = [(6, 0, [overtime_type_id.id])]

    @api.depends('start_date')
    def _get_date(self):
        for record in self:
            record.date = fields.Datetime.now().date()
            if record.start_date:
                start_date_tz = pytz.utc.localize(record.start_date).astimezone(pytz.timezone(record.employee_id._get_tz()))
                record.date = start_date_tz.date()

    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for record in self:
            record.duration = 0.0
            if record.start_date and record.end_date:
                record.duration = (record.end_date - record.start_date).total_seconds() / 3600.0

    def init(self):
        # Avoid duplicated values
        self.env.cr.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS hr_attendance_overtime_with_datetimes_unique_values
            ON %s (employee_id, company_id, attendance_id, start_date, end_date)
            """ % (self._table))


class HrAttendanceOvertimeType(models.Model):
    _name = "hr.attendance.overtime.type"
    _description = "Overtime Type"

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char('Name', required=True, translate=True, readonly=True)
    strategic_name = fields.Char(required=True, readonly=True)
    color = fields.Integer('Color', default=_get_default_color)

    _sql_constraints = [
        ('strategic_name_uniq', 'unique (strategic_name)', "Overtime type already exists!"),
    ]
