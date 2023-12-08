# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    product_bl = fields.Boolean("Ajout article BL", default=False)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

#     @api.onchange('partner_id')
#     def check_user(self):
#         current_user = self.env.user
#         print(current_user.name)
#         print(current_user.product_bl)