# -*- coding: utf-8 -*-
from odoo import models, fields


class Website(models.Model):
    _inherit = "website"

    attachment_ids = fields.Many2many(
        'ir.attachment',
        'website_ir_attachments_rel',
        'website_id',
        'attachment_id',
        domain=[('type', '=', 'binary')],
    )
