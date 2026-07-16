# -*- coding:utf-8 -*-
from datetime import datetime, time

from odoo import api, Command, models, fields, _
import logging

from .hr_work_entry import OVERTIME_WORK_ENTRY_CODES


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    is_undeclared_payslip = fields.Boolean('Is undeclared payslip ?', compute="_define_payslip_nature", default=False,
                                           store=False)

    @api.depends('contract_id')
    def _define_payslip_nature(self):
        for payslip in self:
            payslip.is_undeclared_payslip = False
            if payslip.contract_id and payslip.contract_id.contract_category == 'not_declared':
                payslip.is_undeclared_payslip = True

    is_nd_ticket_payslip = fields.Boolean(
        'Prints the N.D. 80mm ticket ?', compute="_compute_is_nd_ticket_payslip", store=False)

    @api.depends('contract_id', 'struct_id')
    def _compute_is_nd_ticket_payslip(self):
        # Only undeclared payslips whose structure is NOT routed to report_final_settlement
        # (i.e. struct name does not contain 'Solde Tout Compte') keep the dedicated 80mm
        # "PAIEMENT" ticket (report_nd_payslip). This mirrors the exact substring used by
        # _get_pdf_reports, so the "Solde Tout Compte - NA" structure (which DOES contain it)
        # is excluded and follows the standard flow like declared payslips.
        for payslip in self:
            undeclared = bool(payslip.contract_id and payslip.contract_id.contract_category == 'not_declared')
            payslip.is_nd_ticket_payslip = undeclared and 'Solde Tout Compte' not in (payslip.struct_id.name or '')

    overtime_hours_count = fields.Float(compute='_compute_overtime_hours')

    employee_id = fields.Many2one(
        'hr.employee', required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), '|', ('active', '=', True), ('active', '=', False)]")

    def _compute_contract_domain_ids(self):
        for payslip in self:
            payslip.contract_domain_ids = self.env['hr.contract'].search([
                ('company_id', '=', payslip.company_id.id),
                ('employee_id', '=', payslip.employee_id.id),
                ('state', 'in', ['open', 'open_not_declared', 'close']),
            ])

    def action_print_nd_payslip(self):
        return self.env.ref('tanatech_hr_payroll.action_report_nd_payslip').report_action(self)

    def action_open_overtime(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Overtime This Month'),
            'view_mode': 'list,form',
            'res_model': 'hr.attendance.overtime.with.datetimes',
            'domain': [('employee_id', '=', self.employee_id.id), ('date', '>=', self.date_from),
                       ('date', '<=', self.date_to)],
            'context': "{'create': False}",
        }

    @api.depends('date_from', 'date_to', 'employee_id.overtime_with_datetimes_ids.duration',
                 'employee_id.attendance_ids')
    def _compute_overtime_hours(self):
        for payslip in self:
            mapped_validated_overtimes = dict(self.env['hr.attendance.overtime.with.datetimes']._read_group(
                domain=[('date', '>=', payslip.date_from), ('date', '<=', payslip.date_to)],
                groupby=['employee_id'],
                aggregates=['duration:sum']
            ))
            payslip.overtime_hours_count = mapped_validated_overtimes.get(payslip.employee_id, 0)

    def compute_sheet(self):
        for slip in self:
            slip.employee_id.generate_work_entries(
                slip.date_from,
                slip.date_to,
                force=True,
            )
            slip._anchor_overtime_on_nd_contract()

        return super().compute_sheet()

    def _anchor_overtime_on_nd_contract(self):
        """ Overtime (HS) is an N.D. element: its work entries must be anchored
        on the employee's N.D. contract so that they show up on the undeclared
        payslip — the "Solde Tout Compte - NA" one for a leaving employee —
        and never on the declared one. Entries generated before 03/2026 were
        anchored on the declared contract: re-anchor them (scoped to the slip
        period) when (re)computing a payslip.
        """
        self.ensure_one()
        if not self.employee_id or not self.date_from or not self.date_to:
            return
        nd_contract = (
            self.employee_id._get_nd_contract(self.date_from)
            or self.employee_id._get_nd_contract(self.date_to)
        )
        if not nd_contract:
            return
        entries = self.env['hr.work.entry'].search([
            ('employee_id', '=', self.employee_id.id),
            '|',
            ('work_entry_type_id.is_overtime', '=', True),
            ('work_entry_type_id.code', 'in', OVERTIME_WORK_ENTRY_CODES),
            ('state', 'in', ['draft', 'validated']),
            ('contract_id', '!=', nd_contract.id),
            ('contract_id.contract_category', '=', 'declared'),
            ('date_start', '<=', datetime.combine(self.date_to, time.max)),
            ('date_stop', '>=', datetime.combine(self.date_from, time.min)),
        ])
        if entries:
            entries.write({'contract_id': nd_contract.id})

    def _get_pdf_reports(self):
        res = super()._get_pdf_reports()

        if len(self) == 1 and self.struct_id and 'Solde Tout Compte' in self.struct_id.name:
            final_settlement_template = self.env.ref('tanatech_hr_payroll.action_report_final_settlement')
            for payslip in self:
                for report in list(res.keys()):
                    if report != final_settlement_template:
                        res[report] -= payslip

                res[final_settlement_template] |= payslip

        return res
