# -*- coding:utf-8 -*-
from collections import defaultdict

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
            payslip.is_from_undeclared_contract = False

    def _get_nd_capacity_wage(self):
        """ Wage of the employee's "Undeclared" (NA) contract overlapping this
        payslip period.

        It is used as the ceiling that can be absorbed on the NA structure before the
        remainder of an adjustment overflows to the declared structure. """
        self.ensure_one()
        if self.contract_id.contract_category == 'not_declared':
            return self.contract_id.wage
        nd_contract = self.env['hr.contract'].search([
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('contract_category', '=', 'not_declared'),
            ('date_start', '<=', self.date_to),
            '|', ('date_end', '=', False), ('date_end', '>=', self.date_from),
        ], order='date_start desc', limit=1)
        return nd_contract.wage if nd_contract else 0.0

    def _split_salary_attachment_amounts(self, attachments, nd_wage):
        """ Split each adjustment (salary attachment) between the NA (undeclared) and
        declared structures.

        Returns ``{code: {'not_declared': amount, 'declared': amount}}`` where:
        - attachments targeting the declared structure are imputed there in full;
        - attachments targeting the NA structure are imputed on NA up to ``nd_wage``
          (a ceiling shared by all NA-routed adjustments); the uncovered remainder
          overflows to the declared structure.

        This implements: NA salary absorbs the adjustment first, the rest is carried
        over to the declared payslip, and when there is no NA salary (``nd_wage`` = 0)
        the whole adjustment lands on the declared payslip. """
        self.ensure_one()
        declared_by_code = defaultdict(float)
        nd_by_code = defaultdict(float)
        for attachment in attachments:
            code = attachment.other_input_type_id.code
            amount = attachment._get_active_amount()
            if attachment.structure_category == 'declared':
                declared_by_code[code] += amount
            else:
                nd_by_code[code] += amount

        result = defaultdict(lambda: {'not_declared': 0.0, 'declared': 0.0})
        for code, amount in declared_by_code.items():
            result[code]['declared'] += amount

        remaining = nd_wage
        for code in sorted(nd_by_code):
            amount = nd_by_code[code]
            if amount <= 0:
                # Refund / credit: it increases the net, no ceiling to apply.
                result[code]['not_declared'] += amount
                continue
            absorbed = min(amount, remaining) if remaining > 0 else 0.0
            result[code]['not_declared'] += absorbed
            overflow = amount - absorbed
            if overflow > 0:
                result[code]['declared'] += overflow
            remaining -= absorbed
        return result

    def _compute_input_line_ids(self):
        """ Route salary-attachment input lines to the right structure, splitting an
        adjustment between the NA and declared payslips when needed.

        The core method adds every open salary attachment of the employee to every
        payslip regardless of its structure (hence the same advance/deduction was
        imputed twice, once per structure). Here we let it run, then rebuild the
        attachment lines so that:
        - each adjustment is imputed on the structure chosen on the attachment
          (``structure_category``);
        - an NA-routed adjustment is capped at the NA contract wage, the uncovered
          remainder overflowing to the declared payslip;
        - an employee without NA salary gets the whole adjustment on the declared
          payslip (no more negative net on the NA structure). """
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
                # Use the structure *type* category as the source of truth: the stored
                # ``is_declared_type`` on the structure can be stale (it only recomputes
                # when ``type_id`` changes, not when the type's category changes).
                target = 'not_declared' if slip.struct_id.type_id.structure_category == 'not_declared' else 'declared'
                valid_attachments = slip.employee_id.salary_attachment_ids.filtered(
                    lambda a: a.state == 'open'
                    and a.date_start <= slip.date_to
                    and (not a.date_end or a.date_end >= slip.date_from)
                )
                nd_wage = slip._get_nd_capacity_wage()
                amounts_by_code = slip._split_salary_attachment_amounts(valid_attachments, nd_wage)
                for code, amounts in amounts_by_code.items():
                    amount = amounts[target]
                    if not amount:
                        continue
                    attachments = valid_attachments.filtered(
                        lambda a: a.other_input_type_id.code == code
                    )
                    name = ', '.join(attachments.mapped('description'))
                    input_type_id = attachment_types[code].id
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
                name = ' '
                non_declared_contract_id = non_declared_contract[0]
                # Mirror the declared structure on the undeclared side ("Solde
                # Tout Compte" -> "Solde Tout Compte - NA" for an STC), so the
                # N.D. elements (overtime, bonuses...) follow the NA structure.
                non_declared_structure_id = (
                    (payslip.struct_id and payslip.struct_id._get_category_counterpart('not_declared'))
                    or non_declared_contract_id.structure_type_id.default_struct_id
                    or self.env['hr.payroll.structure'].search([('is_declared_type', '=', False)], limit=1)
                )
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
