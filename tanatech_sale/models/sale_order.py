# -*- coding: utf-8 -*-

from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = "sale.order"

    partner_id = fields.Many2one(required=False)
    partner_invoice_id = fields.Many2one(required=False)
    partner_shipping_id = fields.Many2one(required=False)
    pricelist_id = fields.Many2one(required=False)
    is_commercial = fields.Boolean(compute="_compute_is_commercial")
    is_office_design = fields.Boolean(compute="_compute_is_office_design")
    can_edit_pricelist = fields.Boolean(compute="_compute_can_edit_pricelist")

    @api.depends_context('uid')
    def _compute_is_commercial(self):
        for rec in self:
            rec.is_commercial = self.env.user.has_group(
                "tanatech_sale.commercial_group"
            )

    @api.depends_context('uid')
    def _compute_is_office_design(self):
        for rec in self:
            rec.is_office_design = self.env.user.has_group(
                "tanatech_sale.office_design_group"
            )

    @api.depends_context('uid')
    def _compute_can_edit_pricelist(self):
        for rec in self:
            rec.can_edit_pricelist = self.env.user.has_group(
                "tanatech_sale.pricelist_group"
            )
