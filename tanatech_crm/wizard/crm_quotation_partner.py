# -*- coding: utf-8 -*-

from odoo import models, fields, api

class CRMQuotationPartner(models.TransientModel):
    _inherit = 'crm.quotation.partner'

    action = fields.Selection(default='nothing')

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super(CRMQuotationPartner, self).fields_get(allfields, attributes=attributes)
        is_commercial = self.env.user.has_group('tanatech_sale.commercial_group')
        if not is_commercial and len(res['action']['selection']) >= 3:
            if res['action']['selection'][0][0] == 'create':
                res['action']['selection'].pop(0)
            if res['action']['selection'][0][0] == 'exist':
                res['action']['selection'].pop(0)

        return res