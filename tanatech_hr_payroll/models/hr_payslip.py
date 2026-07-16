# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields, _
from odoo.exceptions import UserError
import logging


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

        return super().compute_sheet()

    def _filter_nd_ticket_payslips(self):
        """ Monthly NA payslips: undeclared structure category and not routed to
        the final settlement report. They must only be printed through their
        dedicated 80mm ticket (action_print_nd_payslip). """
        return self.filtered(
            lambda slip: slip.struct_id.type_id.structure_category == 'not_declared'
            and 'Solde Tout Compte' not in (slip.struct_id.name or '')
        )

    def action_print_payslip(self):
        # Guard raised here and not in _get_pdf_reports: that one is also called
        # by _generate_pdf on payslip confirmation, where a UserError would block
        # the validation of an ND-only batch. Here the server action / form button
        # runs in a regular RPC, so the error shows up as a clean dialog instead
        # of the empty zero-page PDF the /print/payslips controller would return.
        printable_payslips = self - self._filter_nd_ticket_payslips()
        if not printable_payslips:
            raise UserError(_(
                "Les bulletins NA s'impriment individuellement via leur ticket "
                "dédié (bouton Imprimer de la fiche)."
            ))
        return super(HrPayslip, printable_payslips).action_print_payslip()

    def _get_pdf_reports(self):
        # Route every "Solde Tout Compte" payslip to the final settlement report,
        # whatever the size of the print batch: this method is the single routing
        # point of the /print/payslips flow (form button and list server action),
        # so the reroute must not be restricted to single-slip prints.
        # The substring criterion matches both STC structures (SD and NA) and is
        # kept in sync with _compute_is_nd_ticket_payslip.
        # Monthly NA payslips are dropped from the mapping: they must never come
        # out of a batch print nor get the standard A4 slip attached on
        # confirmation — their 80mm ticket is the only printable form.
        res = super()._get_pdf_reports()

        final_settlement_template = self.env.ref('tanatech_hr_payroll.action_report_final_settlement')
        stc_payslips = self.filtered(
            lambda slip: slip.struct_id and 'Solde Tout Compte' in slip.struct_id.name
        )
        nd_ticket_payslips = self._filter_nd_ticket_payslips()
        if not stc_payslips and not nd_ticket_payslips:
            return res

        for report in list(res.keys()):
            remaining = res[report] - nd_ticket_payslips
            if report != final_settlement_template:
                remaining -= stc_payslips
            if remaining:
                res[report] = remaining
            else:
                # No slip left on this report: drop the entry so no empty PDF
                # rendering is triggered downstream.
                del res[report]
        if stc_payslips:
            res[final_settlement_template] |= stc_payslips

        return res
