# -*- coding: utf-8 -*-

from odoo import models, fields


class ResCompany(models.Model):
    _inherit = "res.company"

    company_account_number = fields.Char(string="Account number")
    transfer_code = fields.Char(string="Transfer code")
