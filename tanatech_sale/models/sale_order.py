# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
import json

class SaleOrder(models.Model):
    _inherit = "sale.order"

    partner_id = fields.Many2one(required=False)
    partner_invoice_id = fields.Many2one(required=False)
    partner_shipping_id = fields.Many2one(required=False)
    pricelist_id = fields.Many2one(required=False)
    is_commercial = fields.Boolean(compute="_compute_is_commercial")
    is_office_design = fields.Boolean(compute="_compute_is_office_design")
    can_edit_pricelist = fields.Boolean(compute="_compute_can_edit_pricelist")
    show_action_add_service_charge = fields.Boolean()
    # percentage_service_charge = fields.Float(default=0.07)

    @api.onchange('order_line')
    def show_boutton(self):
        for sale in self:
            if sale.order_line:
                sale.show_action_add_service_charge = True
            else:
                sale.show_action_add_service_charge = False


    def _compute_is_commercial(self):
        for rec in self:
            rec.is_commercial = self.env.user.has_group(
                "tanatech_sale.commercial_group"
            )

    def _compute_is_office_design(self):
        for rec in self:
            rec.is_office_design = self.env.user.has_group(
                "tanatech_sale.office_design_group"
            )

    def _compute_can_edit_pricelist(self):
        for rec in self:
            rec.can_edit_pricelist = self.env.user.has_group(
                "tanatech_sale.pricelist_group"
            )

    @api.constrains('order_line')
    def check_have_one_charge_service(self):
        for sale in self:
            if sale.order_line.search([('check_belongs_order', '=', True), ('order_id', '=', sale.id)], limit=1):
                sale.show_action_add_service_charge = False
            else:
                sale.show_action_add_service_charge = True


    def action_add_service_charge(self):
        for order in self:
            product_tmplt = self.env['product.template'].search([('is_product_service_charge', '=', True)], limit=1)
            if product_tmplt:
                self.env['sale.order.line'].create({
                    'product_template_id': product_tmplt.id,
                    'product_id': product_tmplt.product_variant_id.id,
                    'product_uom_qty': 1,
                    'product_uom': product_tmplt.uom_id.id,
                    'price_unit': float(json.loads(self.tax_totals_json)['amount_untaxed']) * product_tmplt.percentage_service_charge,
                    'order_id': order.id,
                    'name': 'Frais de service',
                    'check_belongs_order': True,
                })
            else:
                charge_service_product = self.env['product.template'].create({
                    'name': 'Frais de service',
                    'detailed_type': 'service',
                    'is_product_service_charge': True,
                    'percentage_service_charge': 0.07,
                })
                self.env['sale.order.line'].create({
                    'product_template_id': charge_service_product.id,
                    'product_id': charge_service_product.product_variant_id.id,
                    'product_uom_qty': 1,
                    'product_uom': charge_service_product.uom_id.id,
                    'price_unit': float(json.loads(self.tax_totals_json)['amount_untaxed']) * charge_service_product.percentage_service_charge,
                    'order_id': order.id,
                    'name': 'Frais de service',
                    'check_belongs_order': True,
                })
            order.show_action_add_service_charge = False