# -*- coding:utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, api, _
from odoo.exceptions import UserError


class HrPayslipInputType(models.Model):
    _inherit = 'hr.payslip.input.type'

    available_in_sanction_attachments = fields.Boolean(string="Available in sanction attachments")
