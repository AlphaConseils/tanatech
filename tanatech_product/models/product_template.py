# -*- coding: utf-8 -*-

from odoo import api, models, _
from odoo.tools import format_amount


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    _description = 'Description'

    def get_price_unit_tax_incl(self):
        self.ensure_one()
        price = self.list_price
        res = self.taxes_id.compute_all(
            price, product=self, partner=self.env['res.partner'])
        return res['total_included']