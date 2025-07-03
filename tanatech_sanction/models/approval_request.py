# -*-coding:utf-8-*-

from odoo import models, fields


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    sanction_id = fields.One2many(
        comodel_name="sanction.sanction",
        inverse_name="approval_request_id",
        string="Sanction",
    )
    sanction_count = fields.Integer(compute="_compute_sanction_count")

    def _compute_sanction_count(self):
        for approval in self:
            approval.sanction_count = len(approval.sanction_id.ids)

    def open_sanction_record(self):
        self.ensure_one()
        action = (
            self.sudo()
            .env["ir.actions.actions"]
            ._for_xml_id("tanatech_sanction.sanction_sanction_action")
        )
        sanction = self.get_sanction()
        action.update(
            {"view_mode": "form", "views": [(False, "form")], "res_id": sanction.id}
        )
        return action

    def get_sanction(self):
        return self.env["sanction.sanction"].search(
            [("approval_request_id", "=", self.id)], limit=1
        )
