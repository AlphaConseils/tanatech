# -*- coding:utf-8 -*-
import logging
from collections import defaultdict

from odoo import api, Command, models, fields
from odoo.tools import format_date

_logger = logging.getLogger(__name__)


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

    @api.depends('contract_id.contract_category', 'struct_id.type_id.structure_category')
    def _compute_contract_category(self):
        # NA (undeclared) payslip: undeclared mirror contract or undeclared
        # structure. The 552f225 regression forced False everywhere, which made
        # the declared/undeclared payroll analysis reports mix both worlds.
        for payslip in self:
            payslip.is_from_undeclared_contract = (
                payslip.contract_id.contract_category == 'not_declared'
                or payslip.struct_id.type_id.structure_category == 'not_declared'
            )

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
        """ Override the create method to create the NA (non-declared) mirror
        payslip once a declared one is created individually (outside a batch).

        The ``skip_na_mirror`` context flag short-circuits the whole override:
        it is set on the creation of the mirror itself to cut the recursion,
        and can be used by any caller that must create a payslip without
        triggering the mirror. """
        if self.env.context.get('skip_na_mirror'):
            return super().create(vals_list)
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

    def _create_na_mirror_payslip(self):
        """ Create the NA mirror payslip of this declared payslip through the
        ORM (the historical raw SQL INSERT skipped the name sequence, the
        stored computes and compute_sheet(), leaving an empty NA slip).

        - the NA structure comes from the explicit mapping
          ``struct_id.na_structure_id`` (never "the first not_declared one");
        - the contract is the employee's not_declared mirror contract;
        - if either is missing: clear log and clean abort, no ghost slip. """
        self.ensure_one()
        na_structure = self.struct_id.na_structure_id
        if not na_structure:
            _logger.warning(
                "Fiche NA non créée pour le bulletin %s (id %s) : aucune "
                "structure NA associée (na_structure_id) sur la structure %r.",
                self.name, self.id, self.struct_id.name,
            )
            return self.env['hr.payslip']
        na_contract = self.env['hr.contract'].search([
            ('company_id', '=', self.company_id.id),
            ('employee_id', '=', self.employee_id.id),
            ('contract_category', '=', 'not_declared'),
            ('state', 'in', ['open_not_declared', 'close']),
        ], order='create_date desc', limit=1)
        if not na_contract:
            _logger.warning(
                "Fiche NA non créée pour le bulletin %s (id %s) : aucun "
                "contrat miroir not_declared pour l'employé %r.",
                self.name, self.id, self.employee_id.name,
            )
            return self.env['hr.payslip']
        # hr_payslip.name is required but its stored compute is not
        # precomputed at create time on this codebase (the historical reason
        # for the raw INSERT's name=' '): creating without an explicit name
        # raises a "required field" ValidationError before the compute runs.
        # Build it here with the same format as hr_payroll's _compute_name:
        # "<payslip_name|Salary Slip> - <employee> - <month year>", in the
        # employee's language.
        lang = self.employee_id.lang or self.env.user.lang
        payslip_name = (
            na_structure.with_context(lang=lang).payslip_name
            or self.with_context(lang=lang).env._('Salary Slip')
        )
        na_name = '%s - %s - %s' % (
            payslip_name,
            self.employee_id.name or '',
            format_date(self.env, self.date_from, date_format="MMMM y", lang_code=lang),
        )
        # 1. Create in draft (no state in the vals): the ORM computes the
        #    worked days lines, like the batch wizard flow.
        na_payslip = self.env['hr.payslip'].with_context(skip_na_mirror=True).create({
            'name': na_name,
            'employee_id': self.employee_id.id,
            'contract_id': na_contract.id,
            'struct_id': na_structure.id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'company_id': self.company_id.id,
        })
        # 2. Explicit compute_sheet() while still in draft: salary lines and
        #    NA amount are generated.
        na_payslip.compute_sheet()
        # 3. Align the state on the declared payslip afterwards (the raw SQL
        #    used to copy it at insert time; compute_sheet only runs on
        #    draft/verify slips, hence the alignment comes last).
        if na_payslip.state != self.state:
            na_payslip.state = self.state
        return na_payslip
