# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrSalaryAttachment(models.Model):
    _inherit = 'hr.salary.attachment'

    structure_category = fields.Selection(
        selection=[
            ('declared', "Declared"),
            ('not_declared', "Undeclared (NA)"),
        ],
        string="Salary Structure to Impute",
        compute='_compute_structure_category',
        store=True,
        readonly=False,
        tracking=True,
        help="Salary structure on which the adjustment (advance, deduction, ...) "
             "will be imputed when computing the payslip.",
    )
    can_choose_structure = fields.Boolean(
        string="Structure Choice Allowed",
        compute='_compute_structure_availability',
        help="True when the employee(s) have a salary on both structures "
             "(Declared and Undeclared). Only in that case can the target "
             "salary structure be chosen manually.",
    )

    def _get_salary_structures_presence(self):
        """ Return a tuple ``(has_declared_salary, has_na_salary)`` telling whether
        the attachment's employees hold a running remuneration on the declared and/or
        the "Undeclared" (NA) structure.

        A salary is considered present on a structure when the employee has a
        running contract of the matching category with a wage strictly positive.
        """
        self.ensure_one()
        employees = self.employee_ids
        if not employees:
            return (False, False)
        today = fields.Date.today()
        contracts = self.env['hr.contract'].search([
            ('employee_id', 'in', employees.ids),
            ('state', 'in', ['open', 'open_not_declared']),
            ('wage', '>', 0),
        ]).filtered(
            lambda c: c.date_start <= today and (not c.date_end or c.date_end >= today)
        )
        has_declared = any(c.contract_category == 'declared' for c in contracts)
        has_na = any(c.contract_category == 'not_declared' for c in contracts)
        return (has_declared, has_na)

    @api.depends('employee_ids')
    def _compute_structure_availability(self):
        for attachment in self:
            has_declared, has_na = attachment._get_salary_structures_presence()
            attachment.can_choose_structure = has_declared and has_na

    @api.depends('employee_ids')
    def _compute_structure_category(self):
        for attachment in self:
            has_declared, has_na = attachment._get_salary_structures_presence()
            if has_na and not has_declared:
                # Salary only on the "Undeclared" (NA) structure -> forced to NA.
                attachment.structure_category = 'not_declared'
            elif has_declared and not has_na:
                # No salary on the NA structure -> propose the declared structure.
                attachment.structure_category = 'declared'
            elif has_declared and has_na:
                # Salary on both structures -> keep the user's choice, default to NA
                # (historical behaviour) when nothing has been chosen yet.
                attachment.structure_category = attachment.structure_category or 'not_declared'
            else:
                # No running remuneration found -> fall back on the declared structure
                # to avoid generating a negative amount on the NA structure.
                attachment.structure_category = attachment.structure_category or 'declared'

    @api.constrains('structure_category', 'employee_ids')
    def _check_structure_category(self):
        for attachment in self:
            if attachment.can_choose_structure:
                continue
            has_declared, has_na = attachment._get_salary_structures_presence()
            if has_na and not has_declared and attachment.structure_category != 'not_declared':
                raise ValidationError(_(
                    "The employee only has a salary on the Undeclared (NA) structure: "
                    "the adjustment must be imputed on that structure."
                ))
            if has_declared and not has_na and attachment.structure_category != 'declared':
                raise ValidationError(_(
                    "The employee has no salary on the Undeclared (NA) structure: "
                    "the adjustment must be imputed on the Declared structure."
                ))
