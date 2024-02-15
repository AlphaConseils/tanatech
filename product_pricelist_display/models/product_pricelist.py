# -*- coding: utf-8 -*
from odoo import api, fields, models


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    display_in_products = fields.Boolean("Display in product lists")
