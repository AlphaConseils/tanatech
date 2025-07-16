# Part of Odoo Nexources. 

# Copyright (c) 2025


from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

class HolidaysRequest(models.Model):
    _inherit = "hr.leave"

    sanction_id = fields.Many2one('sanction.sanction', string='Sanction')
    