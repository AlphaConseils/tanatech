# -*- coding: utf-8 -*-


from odoo import _, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _get_aggregated_product_quantities(self, **kwargs):
        res = super()._get_aggregated_product_quantities(**kwargs)
        for key, value in res.items():
            price_unit = value.get('product').x_studio_prix_de_vente
            res[key]['price_unit'] = price_unit
        return res
