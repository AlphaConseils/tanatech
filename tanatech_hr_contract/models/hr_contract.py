# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date
import logging


class HrContract(models.Model):
    _inherit = "hr.contract"

    family_allowance = fields.Monetary(
        "Family Allowance",
        required=True,
        tracking=True,
        help="Employee's monthly family allocation.",
    )