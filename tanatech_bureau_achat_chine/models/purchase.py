# -*- coding: utf-8 -*-
from odoo import models, api


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def create(self, vals):
        if 'user_id' not in vals and self.env.user.has_group('bureau_achat_chine.group_bureau_achat_chine'):
            vals['user_id'] = self.env.user.id
        return super(PurchaseOrder, self).create(vals)
