from odoo import models, fields

class MenuMenu(models.Model):
    _name = 'menu.menu'
    _description = 'Menu'

    name = fields.Char(string='Name', required=True)
