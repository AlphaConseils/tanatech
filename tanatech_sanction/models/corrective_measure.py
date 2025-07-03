# -*-coding: utf-8 -*-
from odoo import fields, models


class SanctionCorrectiveMeasure(models.Model):
    _name = 'sanction.corrective.measure'
    _description = "Corrective Measure"

    name = fields.Char()
    active = fields.Boolean()