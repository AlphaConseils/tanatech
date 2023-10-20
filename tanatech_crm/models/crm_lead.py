# -*- coding: utf-8 -*-

from odoo import models, fields, api


class CRMLead(models.Model):
    _inherit = 'crm.lead'

    partner_id = fields.Many2one(tracking=False)
    contact_name = fields.Char(tracking=False)
    email_from = fields.Char(tracking=False)
    phone = fields.Char(tracking=False)
    is_authorized_pipeline = fields.Boolean(default=True)

    def action_view_sale_quotation(self):
        action = super(CRMLead, self).action_view_sale_quotation()
        if not self.env.user.has_group('tanatech_sale.commercial_group'):
            action.pop('context')
        return action
