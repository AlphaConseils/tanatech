# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from markupsafe import Markup


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    total_ttc = fields.Float(
        string="Total TTC",
        compute="_compute_totals",
        store=True,
    )

    is_create_expenses = fields.Boolean(
        string="Is Create Expenses",
        compute="_compute_is_create_expenses",
    )

    hide_price_and_total = fields.Boolean(
        string="Hide price and total",
        help="If checked, the price and total amount will be hidden in the approval request.",
        related="category_id.hide_price_and_total",
        store=True,
    )

    @api.depends("category_id.approval_type")
    def _compute_is_create_expenses(self):
        for request in self:
            request.is_create_expenses = (
                request.category_id.approval_type == "create_expenses"
            )

    @api.depends("product_line_ids.total")
    def _compute_totals(self):
        for request in self:
            request.total_ttc = sum(line.total for line in request.product_line_ids)

    @api.onchange("product_line_ids")
    def _onchange_product_line_ids(self):
        for request in self:
            if request.is_create_expenses:
                request.amount = sum(line.total for line in request.product_line_ids)

    def action_create_expenses(self):
        self.ensure_one()
        if not self.is_create_expenses:
            return

        created = self.env["hr.expense"]
        for line in self.product_line_ids:
            if line.product_id:
                expense = self.env["hr.expense"].create(
                    {
                        "name": line.product_id.name,
                        "product_id": line.product_id.id,
                        "quantity": line.quantity,
                        "total_amount": line.price * line.quantity,
                        "employee_id": self.x_studio_demandeur.id,
                        "approval_request_id": self.id,
                        "approval_reference": self.name,
                        "approval_date_start": self.date_start,
                        "approval_date_end": self.date_end,
                    }
                )
                created |= expense

        if created:
            lines_html = "".join(
                "<li><a href='/web#id=%d&model=hr.expense'>%s</a></li>" % (e.id, e.name)
                for e in created
            )
            self.message_post(
                body=Markup(_("Expenses created : <ul>%s</ul>")) % Markup(lines_html),
                message_type="notification",
            )
            message = _("Expenses created")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "message": message,
                    "type": "success",
                    "sticky": False,
                    "next": {"type": "ir.actions.act_window_close"},
                },
            }
