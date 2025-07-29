# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    def _generate_payroll_report_fields(self):
        fields_vals_list = []
        is_declared = False
        for rule in self:
            field_name = rule._get_report_field_name()
            if rule.struct_id.is_declared_type:
                model = self.env.ref('hr_payroll.model_hr_payroll_report').sudo().read(['id', 'name'])[0]
                is_declared = True
            else:
                model = self.env.ref('tanatech_hr_contract.model_hr_payroll_undeclared_report').sudo().read(['id', 'name'])[0]
            if rule.appears_on_payroll_report and field_name not in self.env['hr.payroll.report']:
                fields_vals_list.append({
                    'name': field_name,
                    'model': model['name'],
                    'model_id': model['id'],
                    'field_description': '%s: %s' % (rule.struct_id.country_id.code or 'XX', rule.name),
                    'ttype': 'float',
                })
        if fields_vals_list:
            self.env['ir.model.fields'].sudo().create(fields_vals_list)
            if is_declared:
                self.env['hr.payroll.report'].init()
            else:
                self.env['hr.payroll.undeclared.report'].init()

    def _remove_payroll_report_fields(self):
        # Note: should be called after the value is changed, aka after the
        # super call of the write method
        remaining_rules = self.env['hr.salary.rule'].search([('appears_on_payroll_report', '=', True)])
        all_remaining_field_names = [rule._get_report_field_name() for rule in remaining_rules]
        field_names = [rule._get_report_field_name() for rule in self]
        is_declared = all(rule.struct_id.is_declared_type for rule in self)
        # Avoid to unlink a field if another rule request it (example: ONSSEMPLOYER)
        field_names = [field_name for field_name in field_names if field_name not in all_remaining_field_names]
        if is_declared:
            model = self.env.ref('hr_payroll.model_hr_payroll_report')
        else:
            model = self.env.ref('tanatech_hr_contract.model_hr_payroll_undeclared_report')
        fields_to_unlink = self.env['ir.model.fields'].sudo().search([
            ('name', 'in', field_names),
            ('model_id', '=', model.id),
            ('ttype', '=', 'float'),
        ])
        if fields_to_unlink:
            fields_to_unlink.unlink()
            if is_declared:
                self.env['hr.payroll.report'].init()
            else:
                self.env['hr.payroll.undeclared.report'].init()
