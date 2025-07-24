# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import pytz

from collections import defaultdict
from operator import itemgetter

from datetime import datetime, timedelta

from odoo.tools.float_utils import float_is_zero
from odoo import models, fields, api, _
from odoo.osv.expression import AND, OR

class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    # attendance_overtime_id = fields.Many2one('hr.attendance.overtime', string="Attendance Overtime")

    def _update_overtime(self, employee_attendance_dates=None):
        if employee_attendance_dates is None:
            employee_attendance_dates = self._get_attendances_dates()

        overtime_to_unlink = self.env['hr.attendance.overtime']
        overtime_vals_list = []
        is_out_of_working_times = False # useful to determine if the employe is working out of his working times
        affected_employees = self.env['hr.employee']
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

            overtimes = self.env['hr.attendance.overtime'].sudo().search([
                ('employee_id', '=', emp.id),
                ('date', 'in', [day_data[1] for day_data in attendance_dates]),
                ('adjustment', '=', False),
            ])

            company_threshold = emp.company_id.overtime_company_threshold / 60.0
            employee_threshold = emp.company_id.overtime_employee_threshold / 60.0

            for day_data in attendance_dates:
                attendance_date = day_data[1]
                attendances = attendances_per_day.get(attendance_date, self.browse())
                unfinished_shifts = attendances.filtered(lambda a: not a.check_out)
                overtime_duration = 0
                overtime_duration_real = 0
                # Overtime is not counted if any shift is not closed or if there are no attendances for that day,
                # this could happen when deleting attendances.

                # No overtime computed for fully flexible employees
                if emp.is_fully_flexible:
                    continue

                if not unfinished_shifts and attendances:
                    # The employee usually doesn't work on that day
                    if not working_times[attendance_date]:
                        # User does not have any resource_calendar_attendance for that day (week-end for example)
                        overtime_duration = sum(attendances.mapped('worked_hours'))
                        overtime_duration_real = overtime_duration
                        is_out_of_working_times = True
                    # The employee usually work on that day
                    else:
                        # Count time before, during and after 'working hours'
                        pre_work_time, work_duration, post_work_time, planned_work_duration = attendances._get_pre_post_work_time(emp, working_times, attendance_date)
                        # Overtime within the planned work hours + overtime before/after work hours is > company threshold
                        overtime_duration = work_duration - planned_work_duration
                        if pre_work_time > company_threshold:
                            overtime_duration += pre_work_time
                        if post_work_time > company_threshold:
                            overtime_duration += post_work_time
                        # Global overtime including the thresholds
                        overtime_duration_real = sum(attendances.mapped('worked_hours')) - planned_work_duration

                overtime = overtimes.filtered(lambda o: o.date == attendance_date)
                if not float_is_zero(overtime_duration, 2) or unfinished_shifts:
                    # Do not create if any attendance doesn't have a check_out, update if exists
                    if unfinished_shifts:
                        overtime_duration = 0
                    if not overtime and overtime_duration:
                        overtime_vals_list.append({
                            'employee_id': emp.id,
                            'date': attendance_date,
                            'duration': overtime_duration,
                            'duration_real': overtime_duration_real,
                            'attendance_id': self.id,
                            'is_out_of_working_times': is_out_of_working_times
                        })
                    elif overtime:
                        overtime.sudo().write({
                            'duration': overtime_duration,
                            'duration_real': overtime_duration,
                            'is_out_of_working_times': is_out_of_working_times
                        })
                        affected_employees |= overtime.employee_id
                elif overtime:
                    overtime_to_unlink |= overtime
        created_overtimes = self.env['hr.attendance.overtime'].sudo().create(overtime_vals_list)
        employees_worked_hours_to_compute = (affected_employees.ids +
                                             created_overtimes.employee_id.ids +
                                             overtime_to_unlink.employee_id.ids)
        overtime_to_unlink.sudo().unlink()
        to_recompute = self.search([('employee_id', 'in', employees_worked_hours_to_compute)])
        self.env.add_to_compute(self._fields['overtime_hours'],
                                to_recompute)
        self.env.add_to_compute(self._fields['validated_overtime_hours'],
                                to_recompute)
        self.env.add_to_compute(self._fields['expected_hours'],
                                to_recompute)

    # @api.model_create_multi
    # def create(self, vals_list):
    #     """ Create work entry in leaves day if the employee gets to work """
    #     res = super().create(vals_list)
    #     overtime = self.env['hr.attendance.overtime'].search([('attendance_id', '=', res.id)], limit=1)
    #     if overtime.overtime_type == 'special_overtime':
    #         work_entry = self.env['hr.work.entry'].search([('attendance_id', '=', res.id)], limit=1)
    #         if not work_entry:
    #             work_entry_type_overtime = self.env['hr.work.entry.type'].search([('is_overtime', '=', True)], limit=1)
    #             work_entry_type_special = self.env['hr.work.entry.type'].search([('code', '=', 'SPECIALOVERTIME')], limit=1)
    #             new_work_entry = self.env['hr.work.entry'].create({
    #                 'name' : _('{}: {}') % (work_entry_type_overtime.name, overtime.employee_id.name),
    #                 'employee_id' : overtime.employee_id.id,
    #                 'work_entry_type_id' : work_entry_type_special.id,
    #                 'date_start' : res.check_in,
    #                 'date_stop' : res.check_out,
    #                 'duration' : overtime.duration,
    #             })
    #     return res


