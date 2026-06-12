# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[("create_expenses", "Create expenses")],
    )
    hide_price_and_total = fields.Boolean(
        string="Hide price and total",
        help="If checked, the price and total amount will be hidden in the approval request.",
    )
