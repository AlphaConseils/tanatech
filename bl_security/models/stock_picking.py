# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.exceptions import UserError

class ResUsers(models.Model):
    _inherit = 'stock.move'
    
    @api.onchange('product_id')
    def no_creation_product(self):
        for stock_id in self:
            if stock_id.env.user.add_item_bl:
                raise UserError("Vous n'êtes pas autorisé à ajouter un produit")