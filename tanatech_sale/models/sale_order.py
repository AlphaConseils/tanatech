# -*- coding: utf-8 -*-

from odoo import models, fields

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    partner_id = fields.Many2one(required=False)
    partner_invoice_id = fields.Many2one(required=False)
    partner_shipping_id = fields.Many2one(required=False)
    pricelist_id = fields.Many2one(required=False)
    is_commercial = fields.Boolean(compute='_compute_is_commercial')

    def _compute_is_commercial(self):
        for rec in self:
            rec.is_commercial = self.env.user.has_group('tanatech_sale.commercial_group')