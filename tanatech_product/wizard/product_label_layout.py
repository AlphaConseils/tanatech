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
        elif 'tanatechxprice' == self.print_format:
            xml_id = 'tanatech_product.label_product_product_tanatech'
            data['price_included'] = True

        return xml_id, data