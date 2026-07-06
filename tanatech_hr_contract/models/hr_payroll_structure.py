# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    is_declared_type = fields.Boolean('Is declared type ?', compute='_compute_type', store=True)

    @api.depends('type_id', 'type_id.structure_category')
    def _compute_type(self):
        for structure in self:
            if structure.type_id.structure_category == 'declared':
                structure.is_declared_type = True
            else:
                structure.is_declared_type = False