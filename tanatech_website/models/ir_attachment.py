# -*- coding: utf-8 -*-

from odoo import fields, models


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    is_background = fields.Boolean(
        string="Is Background",
        default=False,
    )
