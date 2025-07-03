# -*-coding: utf-8 -*-
from random import randint
from odoo import fields, models


class SanctionType(models.Model):
    _name = "sanction.type"
    _description = "Type of sanction"

    name = fields.Char()
    active = fields.Boolean(default=True)
    is_lay_off = fields.Boolean(string="Lay-off ?")

    def _get_default_color(self):
        return randint(1, 5)

    color = fields.Integer(string="Color", default=_get_default_color)
