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
            product = self.env['product.template'].browse(self.env.context.get('active_id'))
            if product.is_product_variant:
                data['price_tax_included'] = product.taxes_id.compute_all(product.lst_price)['total_included']
            else:
                data['price_tax_included'] = product.taxes_id.compute_all(product.list_price)['total_included']

        return xml_id, data