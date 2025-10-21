# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, time, date, timedelta
from pytz import timezone, utc
from odoo.addons.base.models.res_partner import _tz_get

from odoo import models, fields, api


class HrAttendanceOvertimeResourceCalendarTime(models.Model):
    _name = "hr.attendance.overtime.resource.calendar.time"
    _description = "Time Detail"
    _order = 'hour_from asc'

    name = fields.Char(required=True)

    hour_from = fields.Float(string='Time from', required=True, index=True,
        help="Start and End time of extra hour.\n"
             "A specific value of 24:00 is interpreted as 23:59:59.999999.")
    hour_to = fields.Float(string='Time to', required=True)
    # For the hour duration, the compute function is used to compute the value
    # unambiguously, while the duration in days is computed for the default
    # value based on the day_period but can be manually overridden.
    duration_hours = fields.Float(compute='_compute_duration_hours', string='Duration (hours)')
    overtime_calendar_id = fields.Many2one("hr.attendance.overtime.resource.calendar", string="Overtime Resource's Calendar", required=True, ondelete='cascade')
    day_period = fields.Selection([
        ('day', 'Day'),
        ('night', 'Night')], string='Period', required=True, default='day')

    @api.onchange('hour_from', 'hour_to')
    def _onchange_hours(self):
        # avoid negative or after midnight
        self.hour_from = min(self.hour_from, 23.99)
        self.hour_from = max(self.hour_from, 0.0)
        self.hour_to = min(self.hour_to, 24)
        self.hour_to = max(self.hour_to, 0.0)

        # avoid wrong order
        self.hour_to = max(self.hour_to, self.hour_from)

    @api.depends('hour_from', 'hour_to')
    def _compute_duration_hours(self):
        for time in self:
            time.duration_hours = (time.hour_to - time.hour_from)


class HrAttendanceOvertimeResourceCalendar(models.Model):
    _name = "hr.attendance.overtime.resource.calendar"
    _description = "Overtime Resource Calendar"

    name = fields.Char(required=True)

    company_id = fields.Many2one(
        'res.company', 
        'Company', 
        domain=lambda self: [('id', 'in', self.env.companies.ids)],
        default=lambda self: self.env.company
    )

    time_ids = fields.One2many(
        'hr.attendance.overtime.resource.calendar.time', 
        'overtime_calendar_id', 
        'Extra Hours Time', 
        store=True, 
        readonly=False
    )