# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields
import logging


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    is_deducted_if_weekend_included = fields.Boolean('Is deducted if weekend included', default=False)
