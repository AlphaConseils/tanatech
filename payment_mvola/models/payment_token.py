# -*- coding: utf-8 -*-

from odoo import models, fields


class PaymentToken(models.Model):
    _inherit = "payment.token"

    partner_phone = fields.Char(string="MVola Phone Number")
    correlation_id = fields.Char(string="MVola Correlation ID")
