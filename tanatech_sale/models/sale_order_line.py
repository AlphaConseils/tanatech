# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import fields, models

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    check_belongs_order = fields.Boolean()