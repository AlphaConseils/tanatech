# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ProductTemplate(models.Model):
    _inherit = "product.template"

    wholesaleprice = fields.Float(
        string="Prix de gros", store=True
    )
    wholesaleprice_x = fields.Float(compute="_compute_wholesaleprice")

    def _compute_wholesaleprice(self):
        for product in self:
            product_pricelist_item = self.env["product.pricelist.item"].search(
                    [("product_tmpl_id", "=", product.id)]
                )
            if product_pricelist_item:
                for product_item in product_pricelist_item:
                    product.wholesaleprice_x = product_item.fixed_price
                    x = product.wholesaleprice_x
                    product.wholesaleprice = x
            else:
                product.wholesaleprice_x = False
