# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = "res.partner"

    rcs = fields.Char(string="RCS")
    cin = fields.Char(string="CIN")