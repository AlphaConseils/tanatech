# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    is_from_undeclared_contract = fields.Boolean('Is from undeclared contract ?', compute='_compute_contract_category', store=True)

    net_to_pay_wage = fields.Monetary(
        string="Salaire net à payer",
        compute='_compute_net_to_pay_wage',
        store=True,
    )

    @api.depends('line_ids.total')
    def _compute_net_to_pay_wage(self):
        line_values = self._origin._get_line_values(['SALNETAP'])
        for payslip in self:
            payslip.net_to_pay_wage = line_values['SALNETAP'][payslip._origin.id]['total']

    @api.depends('contract_id')
    def _compute_contract_category(self):
        for payslip in self:
            if payslip.contract_id and payslip.contract_id.contract_category == 'not_declared':
                payslip.is_from_undeclared_contract = True
            else:
                payslip.is_from_undeclared_contract = False

    def _compute_input_line_ids(self):
        """ Restrict salary-attachment input lines to the attachments whose target
        structure (``structure_category``) matches this payslip's structure.

        The core method adds every open salary attachment of the employee to every
        payslip, regardless of its structure. Here we let it run, then rebuild the
        attachment lines keeping only those targeting the current payslip's structure
        (Declared vs Undeclared). This prevents an adjustment (advance, deduction, ...)
        from being imputed on the NA structure for employees who have no NA salary. """
        super()._compute_input_line_ids()
        attachment_types = self._get_attachment_types()
        attachment_type_ids = [f.id for f in attachment_types.values()]
        for slip in self:
            # Drop the attachment lines produced by the core computation...
            lines_to_remove = slip.input_line_ids.filtered(
                lambda x: x.input_type_id.id in attachment_type_ids
            )
            input_line_vals = [Command.unlink(line.id) for line in lines_to_remove]

            if slip.employee_id.salary_attachment_ids and slip.date_to and slip.struct_id:
                slip_category = 'declared' if slip.struct_id.is_declared_type else 'not_declared'
                valid_attachments = slip.employee_id.salary_attachment_ids.filtered(
                    lambda a: a.state == 'open'
                    and a.structure_category == slip_category
                    and a.date_start <= slip.date_to
                    and (not a.date_end or a.date_end >= slip.date_from)
                )
                deduction_types = list(set(valid_attachments.other_input_type_id.mapped('code')))
                for deduction_type in deduction_types:
                    attachments = valid_attachments.filtered(
                        lambda a: a.other_input_type_id.code == deduction_type
                    )
                    amount = attachments._get_active_amount()
                    name = ', '.join(attachments.mapped('description'))
                    input_type_id = attachment_types[deduction_type].id
                    input_line_vals.append(Command.create({
                        'name': name,
                        'amount': amount if not slip.credit_note else -amount,
                        'input_type_id': input_type_id,
                    }))
            slip.update({'input_line_ids': input_line_vals})

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
