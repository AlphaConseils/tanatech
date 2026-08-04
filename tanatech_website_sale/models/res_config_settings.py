# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    website_confirm_sale_activity_user_ids = fields.Many2many(
        related="company_id.website_confirm_sale_activity_user_ids",
        readonly=False,
    )
    website_confirm_delivery_activity_user_ids = fields.Many2many(
        related="company_id.website_confirm_delivery_activity_user_ids",
        readonly=False,
    )
    website_confirm_invoice_activity_user_ids = fields.Many2many(
        related="company_id.website_confirm_invoice_activity_user_ids",
        readonly=False,
    )
