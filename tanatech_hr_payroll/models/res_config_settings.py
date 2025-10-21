# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    overtime_threshold = fields.Integer(
        string="Tolerance Time In Favor Of Company", related='company_id.overtime_threshold', readonly=False)


class ResCompany(models.Model):
    _inherit = 'res.company'

    overtime_threshold = fields.Integer(string="Tolerance Time In Favor Of Company", default=30)