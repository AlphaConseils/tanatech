# -*- coding: utf-8 -*-
from odoo import fields, models
from collections import defaultdict


class ModelName(models.TransientModel):
    _inherit = 'product.label.layout'

    print_format = fields.Selection(selection_add=[
        ('tanatech', 'Format TanaTech'),
        ('tanatechxprice', 'Format TanaTech avec prix')
    ], ondelete={'tanatech': 'set default', 'tanatechxprice': 'set default'})

    def _prepare_report_data(self):
        xml_id, data = super()._prepare_report_data()

        if 'zpl' in self.print_format:
            xml_id = 'stock.label_product_product'
        elif 'tanatech' == self.print_format:
            xml_id = 'tanatech_product.label_product_product_tanatech'
            data['price_included'] = False
            data['products'] = []
            for product in data['quantity_by_product']:
                exist = self.env[data['active_model']].search([('id', '=', product)])
                if exist:
                    data['products'].append(exist)
        elif 'tanatechxprice' == self.print_format:
            xml_id = 'tanatech_product.label_product_product_tanatechxprice'
            data['price_included'] = True
            data['products'] = []
            for product in data['quantity_by_product']:
                exist = self.env[data['active_model']].search([('id', '=', product)])
                if exist:
                    data['products'].append(exist)

        return xml_id, data