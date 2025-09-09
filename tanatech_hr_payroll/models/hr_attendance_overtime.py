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
            ('overtime', "Overtime"),
            ('special_overtime', "Special Overtime"),
            ('hours_worked_on_sunday', "Hours Worked On Sunday"),
            ('hours_worked_on_public_holidays', "Hours Worked On Public Holidays"),
        ],
        string="Overtime Type",
        compute="_compute_overtime_type", 
        tracking=True, 
        readonly=True
    )

    is_out_of_working_times = fields.Boolean('Is out of working times ?', default=False, readonly=True)
    is_within_public_holidays = fields.Boolean('Is within public holidays ?', compute="_compute_overtime_date", readonly=True)
    is_sunday_work = fields.Boolean('Is sunday work ?', compute="_compute_overtime_date", readonly=True)

    is_occasional_night_work = fields.Boolean('Is occasional night work ?', compute="_compute_overtime_date", readonly=True)
    is_usual_night_work = fields.Boolean('Is usual night work ?', compute="_compute_overtime_date", readonly=True)

    # @api.depends('attendance_id.overtime_status')
    # def _compute_state_from_attendance(self):
    #     for overtime in self:
    #         if overtime.attendance_id.overtime_status == "to_approve":
    #             overtime_state = "to_approve"
    #         elif overtime.attendance_id.overtime_status == "approved":
    #             overtime_state = "approved"
    #         else:
    #             overtime_state = "refused"
    #         overtime.state = overtime_state

    @api.depends('date')
    def _compute_overtime_date(self):
        for overtime in self:
            public_holidays = self._get_public_holidays(overtime)
            sundays = self._get_sundays_for_year(overtime.date)
            sundays_without_holidays = [day for day in sundays if day not in public_holidays]
            overtime.is_within_public_holidays = True if overtime.date in public_holidays else False
            overtime.is_sunday_work = True if overtime.date in sundays_without_holidays else False
            overtime.is_occasional_night_work = False
            overtime.is_usual_night_work = False
                
    @api.depends('is_out_of_working_times', 'is_within_public_holidays', 'is_sunday_work')
    def _compute_overtime_type(self):
        for overtime in self:
            if overtime.is_out_of_working_times and not overtime.is_within_public_holidays and not overtime.is_sunday_work:
                overtime.overtime_type = "special_overtime"
            elif overtime.is_within_public_holidays:
                overtime.overtime_type = "hours_worked_on_public_holidays"
            elif overtime.is_sunday_work:
                overtime.overtime_type = "hours_worked_on_sunday"
            else:
                overtime.overtime_type = "overtime"

    # def _update_extra_hours(self, res):
    #     res.write({
    #         'duration' : res.attendance_id.validated_overtime_hours
    #     })

    def _get_public_holidays(self, overtime):
        """
        Fetch all public holidays.
        """
        public_holidays_date_list = []
        public_holidays = self.env['resource.calendar.leaves'].search([
            # ('calendar_id', '=', overtime.employee_id.company_id.resource_calendar_id.id),  #Considering employee's calendar or company
            ('resource_id', '=', False)  # resource_id = False => Public holidays
        ])
        user_tz = timezone(self.env.user.tz or self._context.get('tz') or self.company_id.resource_calendar_id.tz or 'UTC')
        if public_holidays:
            for holiday in public_holidays:
                date_from = utc.localize(holiday.date_from).astimezone(user_tz)
                date_to = utc.localize(holiday.date_to).astimezone(user_tz)
                public_holidays_date_list.append(fields.Date.to_date(date_from))
                public_holidays_date_list.append(fields.Date.to_date(date_to))
        return list(dict.fromkeys(public_holidays_date_list))

    def _get_sundays_for_year(self, selected_date):
        """
        Fetch all sundays in a year.
        """
        sundays = []
        # year = date.today().year
        year = selected_date.year
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() == 6:  # 6 represents Sunday
                sundays.append(current_date)
            current_date += timedelta(days=1)
        return sundays

