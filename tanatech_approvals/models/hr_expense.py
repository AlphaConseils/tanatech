# -*- coding: utf-8 -*-

from odoo import models, fields


class HrExpense(models.Model):
    _inherit = "hr.expense"

    approval_request_id = fields.Many2one(
        comodel_name="approval.request",
        string="Approval Request",
        readonly=True,
    )
    approval_reference = fields.Char(
        string="Reference of the approval request",
    )
    approval_date_start = fields.Datetime(
        string="Date start",
    )
    approval_date_end = fields.Datetime(
        string="Date end",
    )

    def action_open_approval_request(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "approval.request",
            "res_id": self.approval_request_id.id,
            "view_mode": "form",
            "target": "current",
        }
