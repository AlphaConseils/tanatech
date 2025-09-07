# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pytz
from pytz import timezone, utc

from collections import defaultdict
from operator import itemgetter

from datetime import datetime, timedelta, time

from odoo.tools.float_utils import float_is_zero
from odoo import models, fields, api, _
from odoo.osv.expression import AND, OR


class HrAttendanceInherit(models.Model):
    _inherit = "hr.attendance"

    # attendance_overtime_id = fields.Many2one('hr.attendance.overtime', string="Attendance Overtime")

    def unlink(self):
        for att in self:
            existing_overtimes = self.env['hr.attendance.overtime.with.datetimes'].search([('attendance_id', '=', att.id)])
            existing_overtimes.unlink()
        return super().unlink()

    def _remove_duplication_in_list(self, main_list):
        # remove duplicate dicts
        seen = set()
        unique_data = []
        for d in main_list:
            t = tuple(sorted(d.items()))  # make dict hashable
            if t not in seen:
                seen.add(t)
                unique_data.append(d)
        main_list.clear()
        main_list = unique_data
        return main_list

    def _remove_already_existing_records(self, element_list):
        for element in element_list:
            # domain = [
            #     ('employee_id', '=', element['employee_id']),
            #     ('start_date', '=', element['start_date']),
            #     ('end_date', '=', element['end_date']),
            #     ('attendance_id', '=', element['attendance_id']),
            #     ('company_id', '=', element['company_id']),
            # ]
            domain = [(key, '=', value) for key, value in element.items()]
            existing_overtime = self.env['hr.attendance.overtime.with.datetimes'].search(domain)
            if existing_overtime:
                element_list.remove(element)
        return element_list

    def _get_public_holidays(self):
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

    def _get_overtime_out_of_work_day(self, attendances):
        """ split overtime out of work days (sundays and holidays) """
        overtime_on_sunday_before_5_am_vals_list = []
        overtime_on_sunday_between_5am_and_8pm_vals_list = []
        overtime_on_sunday_after_8_pm_vals_list = []
        overtime_on_public_holidays_vals_list = []

        attendance_ofwd_ids = []

        for attendance in attendances:
            # Convert to employee timezone
            employee_tz = pytz.timezone(attendance.employee_id._get_tz())
            local_check_in = pytz.utc.localize(attendance.check_in).astimezone(employee_tz)
            local_check_out = pytz.utc.localize(attendance.check_out).astimezone(employee_tz)

            # Define daily boundaries
            date = local_check_in.date()
            five_am = employee_tz.localize(datetime.combine(date, time(5, 0)))
            eight_pm = employee_tz.localize(datetime.combine(date, time(20, 0)))
            midnight = employee_tz.localize(datetime.combine(date, time(23, 59, 59)))

            public_holidays = self._get_public_holidays()

            # overtime on Sundays
            if date.weekday() == 6:
                # ---- Night before (00:00 – 05:00)
                if local_check_in < five_am:
                    segment_end = min(local_check_out, five_am)
                    if local_check_in < segment_end:
                        overtime_on_sunday_before_5_am_vals_list.append({
                            'employee_id': attendance.employee_id.id,
                            'start_date': local_check_in.astimezone(pytz.utc).replace(tzinfo=None),
                            'end_date': segment_end.astimezone(pytz.utc).replace(tzinfo=None),
                            'attendance_id': attendance.id,
                            'company_id': attendance.employee_id.company_id.id,
                            'overtime_type': 'occasional_night_work_on_weekends',
                        })

                # ---- Day (05:00 – 20:00)
                if local_check_out > five_am and local_check_in < eight_pm:
                    segment_start = max(local_check_in, five_am)
                    segment_end = min(local_check_out, eight_pm)
                    if segment_start < segment_end:
                        overtime_on_sunday_between_5am_and_8pm_vals_list.append({
                            'employee_id': attendance.employee_id.id,
                            'start_date': segment_start.astimezone(pytz.utc).replace(tzinfo=None),
                            'end_date': segment_end.astimezone(pytz.utc).replace(tzinfo=None),
                            'attendance_id': attendance.id,
                            'company_id': attendance.employee_id.company_id.id,
                            'overtime_type': 'day_work_on_sunday',
                        })

                # ---- Night after (20:00 – 24:00)
                if local_check_out > eight_pm:
                    segment_start = max(local_check_in, eight_pm)
                    segment_end = min(local_check_out, midnight)
                    if segment_start < segment_end:
                        overtime_on_sunday_after_8_pm_vals_list.append({
                            'employee_id': attendance.employee_id.id,
                            'start_date': segment_start.astimezone(pytz.utc).replace(tzinfo=None),
                            'end_date': segment_end.astimezone(pytz.utc).replace(tzinfo=None),
                            'attendance_id': attendance.id,
                            'company_id': attendance.employee_id.company_id.id,
                            'overtime_type': 'night_work_on_sunday',
                        })
            elif date in public_holidays:
                overtime_on_public_holidays_vals_list.append({
                    'employee_id': attendance.employee_id.id,
                    'start_date': local_check_in.astimezone(pytz.utc).replace(tzinfo=None),
                    'end_date': local_check_out.astimezone(pytz.utc).replace(tzinfo=None),
                    'attendance_id': attendance.id,
                    'company_id': attendance.employee_id.company_id.id,
                    'overtime_type': 'work_on_public_holidays',
                })
            attendance_ofwd_ids.append(attendance.id)
            
        # # TODO : filter overtime already existing to avoid SQL constraints
        overtime_on_sunday_before_5_am_vals_list = self._remove_already_existing_records(overtime_on_sunday_before_5_am_vals_list)
        overtime_on_sunday_between_5am_and_8pm_vals_list = self._remove_already_existing_records(overtime_on_sunday_between_5am_and_8pm_vals_list)
        overtime_on_sunday_after_8_pm_vals_list = self._remove_already_existing_records(overtime_on_sunday_after_8_pm_vals_list)
        overtime_on_public_holidays_vals_list = self._remove_already_existing_records(overtime_on_public_holidays_vals_list)
        return attendance_ofwd_ids, overtime_on_sunday_before_5_am_vals_list, overtime_on_sunday_between_5am_and_8pm_vals_list, overtime_on_sunday_after_8_pm_vals_list, overtime_on_public_holidays_vals_list

    def _get_overtime_pre_post_work_time(self, employee, working_times, attendance_date):
        overtime_before_working_time = self.env['hr.attendance.overtime.with.datetimes']
        overtime_after_working_time = self.env['hr.attendance.overtime.with.datetimes']

        overtime_before_5_am_working_time_vals_list = []
        overtime_after_5_am_working_time_vals_list = []
        overtime_before_8_pm_working_time_vals_list = []
        overtime_after_8_pm_working_time_vals_list = []

        attendance_ids = []

        # Compute start and end time for that day
        planned_start_dt, planned_end_dt = False, False
        planned_work_duration = 0
        for calendar_attendance in working_times[attendance_date]:
            planned_start_dt = min(planned_start_dt, calendar_attendance[0]) if planned_start_dt else calendar_attendance[0]
            planned_end_dt = max(planned_end_dt, calendar_attendance[1]) if planned_end_dt else calendar_attendance[1]
            planned_work_duration += (calendar_attendance[1] - calendar_attendance[0]).total_seconds() / 3600.0
        for attendance in self:
            # consider check_in as planned_start_dt if within threshold
            # if delta_in < 0: Checked in after supposed start of the day
            # if delta_in > 0: Checked in before supposed start of the day
            local_check_in_emp_tz = pytz.utc.localize(attendance.check_in).astimezone(pytz.timezone(attendance.employee_id._get_tz()))
            local_check_out_emp_tz = pytz.utc.localize(attendance.check_out).astimezone(pytz.timezone(attendance.employee_id._get_tz()))

            # TODO : separate overtimes including in night time and day :
            # - 00:00 to 05:00 for the night
            # - 05:00 to 8:15 (start working time) for the day
            # - 16:30 (end working time) to 20:00 for the day
            # - 20:00 to 24:00 for the night
            employee_tz = pytz.timezone(attendance.employee_id._get_tz())
            five_am = employee_tz.localize(datetime.combine(local_check_in_emp_tz.date(), time(5, 0)))
            eight_pm = employee_tz.localize(datetime.combine(local_check_out_emp_tz.date(), time(20, 0)))

            # ---- BEFORE START OF WORK ----
            if local_check_in_emp_tz < planned_start_dt:
                # Case 1: Overtime fully before 5 AM
                if local_check_out_emp_tz <= five_am:
                    overtime_before_5_am_working_time_vals_list.append({
                        'employee_id': attendance.employee_id.id,
                        'start_date': local_check_in_emp_tz.astimezone(pytz.utc).replace(tzinfo=None),
                        'end_date': local_check_out_emp_tz.astimezone(pytz.utc).replace(tzinfo=None),
                        'attendance_id': attendance.id,
                        'company_id': attendance.employee_id.company_id.id,
                        'overtime_type': 'night_work_on_sunday' if local_check_in_emp_tz.date().weekday() == 0 else 'casual_night_work_on_regular_day',
                    })

                # Case 2: Crosses 5 AM but ends before start of work
                elif five_am < local_check_out_emp_tz <= planned_start_dt:
                    # night part
                    if local_check_in_emp_tz < five_am:
                        overtime_before_5_am_working_time_vals_list.append({
                            'employee_id': attendance.employee_id.id,
                            'start_date': local_check_in_emp_tz.astimezone(pytz.utc).replace(tzinfo=None),
                            'end_date': five_am.astimezone(pytz.utc).replace(tzinfo=None),
                            'attendance_id': attendance.id,
                            'company_id': attendance.employee_id.company_id.id,
                            'overtime_type': 'night_work_on_sunday' if local_check_in_emp_tz.date().weekday() == 0 else 'casual_night_work_on_regular_day',
                        })
                    # day part
                    overtime_after_5_am_working_time_vals_list.append({
                        'employee_id': attendance.employee_id.id,
                        'start_date': five_am.astimezone(pytz.utc).replace(tzinfo=None),
                        'end_date': local_check_out_emp_tz.astimezone(pytz.utc).replace(tzinfo=None),
                        'attendance_id': attendance.id,
                        'company_id': attendance.employee_id.company_id.id,
                        'overtime_type': 'day_work_on_regular_day',
                    })

                # Case 3: Starts before work but ends after planned_start -> cut until planned_start
                else:
                    if local_check_in_emp_tz < five_am:
                        # night part
                        overtime_before_5_am_working_time_vals_list.append({
                            'employee_id': attendance.employee_id.id,
                            'start_date': local_check_in_emp_tz.astimezone(pytz.utc).replace(tzinfo=None),
                            'end_date': five_am.astimezone(pytz.utc).replace(tzinfo=None),
                            'attendance_id': attendance.id,
                            'company_id': attendance.employee_id.company_id.id,
                            'overtime_type': 'casual_night_work_on_regular_day',
                        })
                    # day part
                    overtime_after_5_am_working_time_vals_list.append({
                        'employee_id': attendance.employee_id.id,
                        'start_date': max(local_check_in_emp_tz, five_am).astimezone(pytz.utc).replace(tzinfo=None),
                        'end_date': planned_start_dt.astimezone(pytz.utc).replace(tzinfo=None),
                        'attendance_id': attendance.id,
                        'company_id': attendance.employee_id.company_id.id,
                        'overtime_type': 'day_work_on_regular_day',
                    })

            # ---- AFTER END OF WORK ----
            if local_check_out_emp_tz > planned_end_dt:
                # Case 1: Entirely between end and 8pm
                if planned_end_dt < local_check_out_emp_tz <= eight_pm:
                    overtime_before_8_pm_working_time_vals_list.append({
                        'employee_id': attendance.employee_id.id,
                        'start_date': max(local_check_in_emp_tz, planned_end_dt).astimezone(pytz.utc).replace(tzinfo=None),
                        'end_date': local_check_out_emp_tz.astimezone(pytz.utc).replace(tzinfo=None),
                        'attendance_id': attendance.id,
                        'company_id': attendance.employee_id.company_id.id,
                        'overtime_type': 'day_work_on_regular_day',
                    })

                # Case 2: Crosses 8pm -> split into day + night
                else:
                    # day part (until 8pm)
                    if local_check_in_emp_tz < eight_pm:
                        overtime_before_8_pm_working_time_vals_list.append({
                            'employee_id': attendance.employee_id.id,
                            'start_date': max(local_check_in_emp_tz, planned_end_dt).astimezone(pytz.utc).replace(tzinfo=None),
                            'end_date': eight_pm.astimezone(pytz.utc).replace(tzinfo=None),
                            'attendance_id': attendance.id,
                            'company_id': attendance.employee_id.company_id.id,
                            'overtime_type': 'day_work_on_regular_day',
                        })
                    # night part (after 8pm)
                    overtime_after_8_pm_working_time_vals_list.append({
                        'employee_id': attendance.employee_id.id,
                        'start_date': max(local_check_in_emp_tz, eight_pm).astimezone(pytz.utc).replace(tzinfo=None),
                        'end_date': local_check_out_emp_tz.astimezone(pytz.utc).replace(tzinfo=None),
                        'attendance_id': attendance.id,
                        'company_id': attendance.employee_id.company_id.id,
                        'overtime_type': 'occasional_night_work_on_weekends' if local_check_in_emp_tz.date().weekday() == 5 else 'casual_night_work_on_regular_day',
                    })
            attendance_ids.append(attendance.id)

        # # TODO : filter overtime already existing to avoid SQL constraints
        overtime_before_5_am_working_time_vals_list = self._remove_already_existing_records(overtime_before_5_am_working_time_vals_list)
        overtime_after_5_am_working_time_vals_list = self._remove_already_existing_records(overtime_after_5_am_working_time_vals_list)
        overtime_before_8_pm_working_time_vals_list = self._remove_already_existing_records(overtime_before_8_pm_working_time_vals_list)
        overtime_after_8_pm_working_time_vals_list = self._remove_already_existing_records(overtime_after_8_pm_working_time_vals_list)
        return attendance_ids, overtime_before_5_am_working_time_vals_list, overtime_after_5_am_working_time_vals_list, overtime_before_8_pm_working_time_vals_list, overtime_after_8_pm_working_time_vals_list

    def _update_overtime(self, employee_attendance_dates=None):
        if employee_attendance_dates is None:
            employee_attendance_dates = self._get_attendances_dates()

        overtimes_to_unlink = self.env['hr.attendance.overtime.with.datetimes']
        # regular overtime
        overtime_before_5_am_vals_list = []
        overtime_after_5_am_vals_list = []
        overtime_before_8_pm_vals_list = []
        overtime_after_8_pm_vals_list = []
        # out of work day overtime
        overtime_on_sunday_before_5_am_vals_list = []
        overtime_on_sunday_between_5am_and_8pm_vals_list = []
        overtime_on_sunday_after_8_pm_vals_list = []
        overtime_on_public_hoilday_vals_list = []

        for emp, attendance_dates in employee_attendance_dates.items():
            # get_attendances_dates returns the date translated from the local timezone without tzinfo,
            # and contains all the date which we need to check for overtime
            attendance_domain = []
            for attendance_date in attendance_dates:
                attendance_domain = OR([attendance_domain, [
                    ('check_in', '>=', attendance_date[0]), ('check_in', '<', attendance_date[0] + timedelta(hours=24)),
                ]])
            attendance_domain = AND([[('employee_id', '=', emp.id)], attendance_domain])

            # Attendances per LOCAL day
            attendances_per_day = defaultdict(lambda: self.env['hr.attendance'])
            all_attendances = self.env['hr.attendance'].search(attendance_domain)
            for attendance in all_attendances:
                check_in_day_start = attendance._get_day_start_and_day(attendance.employee_id, attendance.check_in)
                attendances_per_day[check_in_day_start[1]] += attendance

            # As _attendance_intervals_batch and _leave_intervals_batch both take localized dates we need to localize those date
            start = pytz.utc.localize(min(attendance_dates, key=itemgetter(0))[0])
            stop = pytz.utc.localize(max(attendance_dates, key=itemgetter(0))[0] + timedelta(hours=24))

            # Retrieve expected attendance intervals
            calendar = emp.resource_calendar_id or emp.company_id.resource_calendar_id
            expected_attendances = emp._employee_attendance_intervals(start, stop)

            # working_times = {date: [(start, stop)]}
            working_times = defaultdict(lambda: [])
            for expected_attendance in expected_attendances:
                # Exclude resource.calendar.attendance
                working_times[expected_attendance[0].date()].append(expected_attendance[:2])

            overtimes_with_datetimes = self.env['hr.attendance.overtime.with.datetimes'].sudo().search([
                ('employee_id', '=', emp.id),
                ('date', 'in', [day_data[1] for day_data in attendance_dates]),
            ])

            company_threshold = emp.company_id.overtime_company_threshold / 60.0
            employee_threshold = emp.company_id.overtime_employee_threshold / 60.0

            for day_data in attendance_dates:
                attendance_date = day_data[1]
                attendances = attendances_per_day.get(attendance_date, self.browse())
                unfinished_shifts = attendances.filtered(lambda a: not a.check_out)

                att_ids = []
                
                # Overtime is not counted if any shift is not closed or if there are no attendances for that day,
                # this could happen when deleting attendances.

                # No overtime computed for fully flexible employees
                if emp.is_fully_flexible:
                    continue

                if not unfinished_shifts and attendances:
                    # The employee usually doesn't work on that day
                    if not working_times[attendance_date]:
                        # User does not have any resource_calendar_attendance for that day (week-end for example)
                        # overtimes on sundays or public holidays
                        attendance_ofwd_ids, m, n, o, p = self._get_overtime_out_of_work_day(attendances)
                        att_ids += attendance_ofwd_ids
                        overtime_on_sunday_before_5_am_vals_list = m
                        overtime_on_sunday_between_5am_and_8pm_vals_list = n
                        overtime_on_sunday_after_8_pm_vals_list = o
                        overtime_on_public_hoilday_vals_list = p
                    # The employee usually work on that day
                    else:
                        # Count time before, during and after 'working hours'
                        attendance_ids, pre_work_time_overtime_before_5_am_vals_list, pre_work_time_overtime_after_5_am_vals_list, post_work_time_overtime_before_8_pm_vals_list, post_work_time_overtime_after_8_pm_vals_list = attendances._get_overtime_pre_post_work_time(emp, working_times, attendance_date)
                        att_ids += attendance_ids
                        overtime_before_5_am_vals_list = pre_work_time_overtime_before_5_am_vals_list
                        overtime_after_5_am_vals_list = pre_work_time_overtime_after_5_am_vals_list
                        overtime_before_8_pm_vals_list = post_work_time_overtime_before_8_pm_vals_list
                        overtime_after_8_pm_vals_list = post_work_time_overtime_after_8_pm_vals_list

        # remove duplicate dicts
        # regular overtime
        overtime_before_5_am_vals_list = self._remove_duplication_in_list(overtime_before_5_am_vals_list)
        overtime_after_5_am_vals_list = self._remove_duplication_in_list(overtime_after_5_am_vals_list)
        overtime_before_8_pm_vals_list = self._remove_duplication_in_list(overtime_before_8_pm_vals_list)
        overtime_after_8_pm_vals_list = self._remove_duplication_in_list(overtime_after_8_pm_vals_list)
        # out of work day overtime
        overtime_on_sunday_before_5_am_vals_list = self._remove_duplication_in_list(overtime_on_sunday_before_5_am_vals_list)
        overtime_on_sunday_between_5am_and_8pm_vals_list = self._remove_duplication_in_list(overtime_on_sunday_between_5am_and_8pm_vals_list)
        overtime_on_sunday_after_8_pm_vals_list = self._remove_duplication_in_list(overtime_on_sunday_after_8_pm_vals_list)
        overtime_on_public_hoilday_vals_list = self._remove_duplication_in_list(overtime_on_public_hoilday_vals_list)
        # create overtimes with datetimes
        # regular overtime
        created_overtimes_with_datetimes_before_5_am = self.env['hr.attendance.overtime.with.datetimes'].sudo().create(overtime_before_5_am_vals_list)
        created_overtimes_with_datetimes_after_5_am = self.env['hr.attendance.overtime.with.datetimes'].sudo().create(overtime_after_5_am_vals_list)
        created_overtimes_with_datetimes_before_8_pm = self.env['hr.attendance.overtime.with.datetimes'].sudo().create(overtime_before_8_pm_vals_list)
        created_overtimes_with_datetimes_after_8_pm = self.env['hr.attendance.overtime.with.datetimes'].sudo().create(overtime_after_8_pm_vals_list)
        # out of work day overtime
        created_overtime_on_sunday_before_5_am = self.env['hr.attendance.overtime.with.datetimes'].sudo().create(overtime_on_sunday_before_5_am_vals_list)
        created_overtimes_on_sunday_between_5am_and_8pm = self.env['hr.attendance.overtime.with.datetimes'].sudo().create(overtime_on_sunday_between_5am_and_8pm_vals_list)
        created_overtimes_on_sunday_after_8_pm = self.env['hr.attendance.overtime.with.datetimes'].sudo().create(overtime_on_sunday_after_8_pm_vals_list)
        created_overtimes_on_public_hoilda = self.env['hr.attendance.overtime.with.datetimes'].sudo().create(overtime_on_public_hoilday_vals_list)
