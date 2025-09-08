# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields, _
import logging

from datetime import date, datetime
import pytz

class HrWorkEntry(models.Model):
    _inherit = 'hr.work.entry'

    is_just_to_trigger_depends_method = fields.Boolean('Nothing but trigger', compute="_compute_check_overtime_work_entry_type", default=False, store=True)
    nothing_but_trigger = fields.Boolean('Nothing but trigger', compute="_compute_overtime_work_entry_type", default=False, store=True)

    work_entry_type_id = fields.Many2one('hr.work.entry.type', store=True)

    @api.depends('work_entry_type_id')
    def _compute_check_overtime_work_entry_type(self):
        for entry in self:
            date_start_tz = pytz.utc.localize(entry.date_start).astimezone(pytz.timezone(entry.employee_id._get_tz()))
            overtimes = self.env['hr.attendance.overtime.with.datetimes'].search([('date', '=', date_start_tz.date())])
            work_entries_vals = []
            for overtime in overtimes:
                work_type_domain = []
                if overtime.overtime_type == 'day_work_on_regular_day':
                    work_type_domain = [('code', '=', 'DAYWORKONREGULARDAY')]
                elif overtime.overtime_type == 'casual_night_work_on_regular_day':
                    work_type_domain = [('code', '=', 'CASUALNIGHTWORKONREGULARDAY')]
                elif overtime.overtime_type == 'occasional_night_work_on_weekends':
                    work_type_domain = [('code', '=', 'OCCASIONALNIGHTWORKONWEEKENDS')]
                elif overtime.overtime_type == 'day_work_on_sunday':
                    work_type_domain = [('code', '=', 'DAYWORKONSUNDAY')]
                elif overtime.overtime_type == 'night_work_on_sunday':
                    work_type_domain = [('code', '=', 'NIGHTWORKONSUNDAY')]
                elif overtime.overtime_type == 'work_on_public_holidays':
                    work_type_domain = [('code', '=', 'WORKONPUBLICHOLIDAYS')]
                else:
                    work_type_domain = [('id', '=', 0)]
                work_entry_type = self.env['hr.work.entry.type'].search(work_type_domain)
                work_entries_vals.append({
                    'name' : '%s: %s' % (work_entry_type.name, overtime.employee_id.name),
                    'date_start' : pytz.utc.localize(overtime.start_date).astimezone(pytz.timezone(overtime.employee_id._get_tz())).replace(tzinfo=None),
                    'date_stop' : pytz.utc.localize(overtime.end_date).astimezone(pytz.timezone(overtime.employee_id._get_tz())).replace(tzinfo=None),
                    'work_entry_type_id' : work_entry_type.id if work_entry_type else False,
                    'employee_id' : overtime.employee_id.id,
                    'contract_id' : overtime.employee_id.contract_id.id,
                    'company_id' : overtime.employee_id.company_id.id,
                    'state' : 'draft',
                })
            # d = entry.date_start.date()
            start_of_day = datetime.combine(date_start_tz.date(), datetime.min.time())
            end_of_day = datetime.combine(date_start_tz.date(), datetime.max.time())
            existing_work_entries = self.env['hr.work.entry'].search([('date_start', '>=', start_of_day), ('date_stop', '<=', end_of_day), ('work_entry_type_id.is_overtime', '=', True)])
            # existing_work_entries.write({'active': False})
            existing_work_entries.unlink()
            if work_entries_vals:
                self.env['hr.work.entry'].create(work_entries_vals)
            entry.is_just_to_trigger_depends_method = True

    # @api.depends('work_entry_type_id')
    # def _compute_check_overtime_work_entry_type(self):
    #     for entry in self:
    #         if entry.work_entry_type_id.is_overtime:
    #             entry.is_just_to_trigger_depends_method = True

    # @api.depends('is_just_to_trigger_depends_method')
    # def _compute_overtime_work_entry_type(self):
    #     for entry in self:
    #         if entry.is_just_to_trigger_depends_method:
    #             overtime = self.env['hr.attendance.overtime'].search([('attendance_id', '=', entry.attendance_id.id)])
    #             logging.info('start')
    #             if overtime.overtime_type == 'special_overtime':
    #                 work_entry_type_special = self.env['hr.work.entry.type'].search([('code', '=', 'SPECIALOVERTIME')], limit=1)
    #                 entry.nothing_but_trigger = not entry.nothing_but_trigger
    #                 # entry.write({'work_entry_type_id' : work_entry_type_special.id})
    #                 work_entry_name = f"{work_entry_type_special.name}: {entry.employee_id.name}"
    #                 self._sql_request(work_entry_type_special.id, work_entry_name, entry.id)
    #             elif overtime.overtime_type == 'hours_worked_on_sunday':
    #                 work_entry_type_sunday = self.env['hr.work.entry.type'].search([('code', '=', 'SUNDAYOVERTIME')], limit=1)
    #                 entry.nothing_but_trigger = not entry.nothing_but_trigger
    #                 # entry.write({'work_entry_type_id' : work_entry_type_sunday.id})
    #                 work_entry_name = f"{work_entry_type_sunday.name}: {entry.employee_id.name}"
    #                 self._sql_request(work_entry_type_sunday.id, work_entry_name, entry.id)
    #             elif overtime.overtime_type == 'hours_worked_on_public_holidays':
    #                 work_entry_type_public_holiday = self.env['hr.work.entry.type'].search([('code', '=', 'PUBLICHOLIDAYOVERTIME')], limit=1)
    #                 entry.nothing_but_trigger = not entry.nothing_but_trigger
    #                 # entry.write({'work_entry_type_id' : work_entry_type_public_holiday.id})
    #                 work_entry_name = f"{work_entry_type_public_holiday.name}: {entry.employee_id.name}"
    #                 self._sql_request(work_entry_type_public_holiday.id, work_entry_name, entry.id)
    #             else:
    #                 entry.nothing_but_trigger = not entry.nothing_but_trigger

    # def _sql_request(self, work_entry_type_id, work_entry_name, work_entry_id):
    #     self.env.cr.execute("""
    #         UPDATE hr_work_entry
    #         SET work_entry_type_id = %s, name = %s
    #         WHERE id = %s; 
    #     """, (work_entry_type_id, work_entry_name, work_entry_id))
    #     self.env.cr.commit()

class HrWorkEntryType(models.Model):
    _inherit = 'hr.work.entry.type'

    is_overtime = fields.Boolean('Is overtime')
    is_readonly_code = fields.Boolean()

    