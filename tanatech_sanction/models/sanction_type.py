# -*-coding: utf-8 -*-
from random import randint
from odoo import fields, models


class SanctionType(models.Model):
    _name = "sanction.type"
    _description = "Type of sanction"

    name = fields.Char()
    active = fields.Boolean(default=True)
    is_lay_off = fields.Boolean(string="Lay-off ?")
    code = fields.Char(string="Code")

    is_taken_into_account_in_time_off = fields.Boolean(string="Include in Time-off ?")

    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string="Type de congé associé",
        help="Type de congé généré automatiquement en Congés/Paie pour ce type de sanction.",
    )
    
    def _get_default_color(self):
        return randint(1, 5)

    color = fields.Integer(string="Color", default=_get_default_color)
