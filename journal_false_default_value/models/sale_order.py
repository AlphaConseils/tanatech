# -*- coding: utf-8 -*-

from odoo import models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _prepare_invoice(self):
        return {
            **super(SaleOrder, self)._prepare_invoice(),
            'journal_id': False
        }