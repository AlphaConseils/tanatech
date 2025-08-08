# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from datetime import datetime, time, date, timedelta
from pytz import timezone, utc

from odoo import models, fields, api

class HrAttendanceOvertime(models.Model):
    _name = "hr.attendance.overtime"
    _inherit = ["hr.attendance.overtime", "mail.thread"]

    attendance_id = fields.Many2one('hr.attendance', string="Attendance")

    state = fields.Selection(
        selection=[
            ('to_approve', "To Approve"),
            ('approved', "Approved"),
            ('refused', "Refused")
        ], 
        # related='attendance_id.overtime_status',
        string="State",
        compute="_compute_state_from_attendance", 
        store=True, 
        tracking=True, 
        readonly=True
    )

    registration_number = fields.Char(
        string="Registration number", related="employee_id.registration_number"
    )

    overtime_type = fields.Selection(
        selection=[
            ('overtime_130', "Overtime at 130%"),
            ('overtime_150', "Overtime at 150%"),
            ('usual_night_work_30', "Usual Night Work at 30%"),
            ('usual_night_work_50', "Usual Night Work at 50%"),
            ('hours_worked_on_sunday', "Hours Worked On Sunday"),
            ('hours_worked_on_public_holidays', "Hours Worked On Public Holidays"),
        ],
        related='attendance_id.overtime_type',
        string="Overtime Type",
        tracking=True, 
        readonly=True
    )

    @api.depends('attendance_id.overtime_status')
    def _compute_state_from_attendance(self):
        for overtime in self:
            if overtime.attendance_id.overtime_status == "to_approve":
                overtime_state = "to_approve"
            elif overtime.attendance_id.overtime_status == "approved":
                overtime_state = "approved"
            else:
                overtime_state = "refused"
            overtime.state = overtime_state

