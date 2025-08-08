# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields
import logging


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    classification = fields.Char(string='Classification')
    indice = fields.Char(string='Indice')