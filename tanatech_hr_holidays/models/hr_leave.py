# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields

from datetime import datetime, time, date, timedelta
from pytz import timezone, utc
import logging


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    leave_friday_end_increases_duration = fields.Boolean('Friday end date increased duration', default=False, compute="_compute_duration")
    leave_weekend_included_increases_duration = fields.Boolean('Friday end date increased duration', default=False, compute="_compute_duration")

    @api.depends('date_from', 'date_to', 'resource_calendar_id', 'holiday_status_id.request_unit')
    def _compute_duration(self):
        durations = self._get_durations()
        for leave in self:
            days, hours = durations[leave.id]
            leave.number_of_hours = hours
            leave.number_of_days = days

            leave_friday_end = False
            leave_weekend_included = False
            if leave.holiday_status_id.is_deducted_if_weekend_included:
                fridays = self._get_fridays(leave.date_from.date(), leave.date_to.date())
                
                if leave.date_to.date() in fridays:
                    leave.number_of_days = days + 3
                    added_hours = (hours / days) * 3
                    leave.number_of_hours = hours + added_hours
                    leave_friday_end = True
                    
                weekends_number = self._count_weekends(leave.date_from.date(), leave.date_to.date())
                if weekends_number > 0:
                    leave.number_of_days = leave.number_of_days + (weekends_number)
                    added_hours = (hours / days) * (weekends_number)
                    leave.number_of_hours = leave.number_of_hours + added_hours
                    leave_weekend_included = True
                    
            leave.leave_friday_end_increases_duration = leave_friday_end
            leave.leave_weekend_included_increases_duration = leave_weekend_included

    def _get_fridays(self, start_date, end_date):
        """
        Return a list of all Fridays between start_date and end_date (inclusive).
        """
        fridays = []
        current = start_date
        while current <= end_date:
            if current.weekday() == 4:  # 4 = Friday
                fridays.append(current)
            current += timedelta(days=1)
        return fridays

    def _count_weekends(self, start_date, end_date):
        """
        Count Saturdays and Sundays between start_date and end_date (inclusive).
        """
        count = 0
        current = start_date
        while current <= end_date:
            if current.weekday() in (5, 6):  # 5 = Saturday, 6 = Sunday
                count += 1
            current += timedelta(days=1)
        return count