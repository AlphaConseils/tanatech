from odoo import models, fields, api


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'
    
    is_wholesaleprices = fields.Boolean()
    