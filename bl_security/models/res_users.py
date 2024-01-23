# -*- coding: utf-8 -*-
from odoo import models, fields

class ResUsers(models.Model):
    _inherit = 'res.users'

    add_item_bl = fields.Boolean(string='blocage ajout BL', default=False)