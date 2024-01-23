# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    product_bl = fields.Boolean("Ajout article BL", default=False)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    