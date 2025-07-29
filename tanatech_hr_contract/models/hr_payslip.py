# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    is_from_undeclared_contract = fields.Boolean('Is from undeclared contract ?', compute='_compute_contract_category', store=True)

    structure_domain_ids = fields.Many2many('hr.payroll.structure', compute='_compute_structure_domain_ids')

    @api.depends('contract_id')
    def _compute_contract_category(self):
        for payslip in self:
            if payslip.contract_id and payslip.contract_id.contract_category == 'not_declared':
                payslip.is_from_undeclared_contract = True
            else:
                payslip.is_from_undeclared_contract = False

    @api.depends('contract_id')
    def _compute_structure_domain_ids(self):
        for payslip in self:
            if payslip.contract_id.contract_category == 'declared':
                payslip.structure_domain_ids = self.env['hr.payroll.structure'].search([('is_declared_type', '=', True)])
            else:
                payslip.structure_domain_ids = self.env['hr.payroll.structure'].search([('is_declared_type', '=', False)])
