# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields
import logging


class ResourceCalendar(models.Model):
    _inherit = 'resource.calendar'

    is_night_shift = fields.Boolean('Is night shift ?', default=False)