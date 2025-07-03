# -*- coding:utf-8 -*-
from odoo import models, fields


class HrEmployeeBase(models.AbstractModel):
    _inherit = 'hr.employee.base'

    sanction_ids = fields.One2many(comodel_name='sanction.sanction', inverse_name='employee_id', domain=[('state', '!=', 'draft')])
    sanction_count = fields.Integer(compute='_compute_sanction_count') 

    def get_sanction(self):
        self.ensure_one()
        sanctions = self.env['sanction.sanction'].search([('state', '!=', 'draft'),('employee_id', '=', self.id)])
        if len(sanctions) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Sanctions',
                'view_mode': 'form',
                'res_model': 'sanction.sanction',
                'res_id': sanctions.id,
                'context': "{'create': False}",
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sanctions',
            'view_mode': 'list,form',
            'res_model': 'sanction.sanction',
            'domain': [('employee_id', '=', self.id)],
            'context': "{'create': False}",
        }
    
    def _compute_sanction_count(self):
        for employee in self:
            employee.sanction_count = self.env['sanction.sanction'].search_count([
                ('state', '!=', 'draft'),
                ('employee_id', '=', employee.id)
                ])
