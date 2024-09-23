# -*- coding: utf-8 -*-

from odoo import models


class ProductPricelistReport(models.AbstractModel):
    _inherit = "report.product.report_pricelist"

    def _get_product_data(self, is_product_tmpl, product, pricelist, quantities):
        res = super(ProductPricelistReport, self)._get_product_data(
            is_product_tmpl, product, pricelist, quantities
        )
        default_code = product.default_code
        list_price = product.list_price
        qty_available = product.qty_available
        is_in_stock = False
        if qty_available > 0.0:
            is_in_stock = True
        else:
            is_in_stock = False
        res.update(
            {
                "default_code": default_code,
                "list_price": list_price,
                "is_in_stock": is_in_stock,
            }
        )
        return res
