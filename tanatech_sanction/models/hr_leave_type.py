# Part of Odoo Nexources. 

# Copyright (c) 2025


from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

class HolidaysType(models.Model):
    _inherit = "hr.leave.type"

    specific_for_sanction = fields.Boolean('Sanction included', default=False, help="It is just for linking time off to sanction.")
    