# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields
import logging


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'
