# -*- coding: utf-8 -*-
from werkzeug.exceptions import HTTPException

from odoo.http import request

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
