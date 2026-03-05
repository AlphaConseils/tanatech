# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    is_from_undeclared_contract = fields.Boolean('Is from undeclared contract ?', compute='_compute_contract_category', store=True)

    @api.depends('contract_id')
    def _compute_contract_category(self):
        for payslip in self:
            if payslip.contract_id and payslip.contract_id.contract_category == 'not_declared':
                payslip.is_from_undeclared_contract = True
            else:
                payslip.is_from_undeclared_contract = False

    @api.model_create_multi
    def create(self, vals_list):
        """ 
        Override the create method to create a non-declared payslip once a declared one is created.
        """
        res = super().create(vals_list)
        for payslip in res:
            if payslip.contract_id.contract_category == 'declared' and not payslip.payslip_run_id:
                # contract = vals.get('contract_id')
                # employee = vals.get('employee_id')
                non_declared_contract = self.env['hr.contract'].search([
                    ('company_id', '=', payslip.company_id.id),
                    ('employee_id', '=', payslip.employee_id.id),
                    ('contract_category', '=', 'not_declared'),
                    ('state', 'in', ['open_not_declared', 'close']),
                ], order='create_date desc')
                non_declared_structure = self.env['hr.payroll.structure'].search([
                    ('is_declared_type', '=', False)
                ])
                name = ' '
                non_declared_contract_id = non_declared_contract[0]
                non_declared_structure_id = non_declared_structure[0]
                date_from = payslip.date_from
                date_to = payslip.date_to
                state = payslip.state
                company_id = payslip.company_id.id
                
                self.env.cr.execute("""
                        INSERT INTO hr_payslip (name, employee_id, contract_id, struct_id, date_from, date_to, company_id, state)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """,
                    [
                        name,
                        payslip.employee_id.id, 
                        non_declared_contract_id.id, 
                        non_declared_structure_id.id, 
                        date_from, 
                        date_to, 
                        company_id, 
                        state
                    ]
                )
                # self.env.cr.execute(query)
                # self.env.cr.commit()
                not_declared_payslip_id = self.env.cr.fetchone()
                created_not_declared_payslip_id = self.env['hr.payslip'].search([('id', '=', not_declared_payslip_id)], limit=1)
                created_not_declared_payslip_id._compute_worked_days_line_ids()
        return res
