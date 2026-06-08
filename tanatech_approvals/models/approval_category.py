# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[("create_expenses", "Create expenses")],
    )
