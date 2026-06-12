# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ApprovalProductLine(models.Model):
    _inherit = "approval.product.line"

    price = fields.Float(
        string="Price",
        help="Price unit (TTC)",
        compute="_compute_price",
        store=True,
        readonly=False,
    )

    total = fields.Float(
        string="Total",
        help="Total price (Price × Quantity)",
        compute="_compute_total",
        store=True,
        readonly=False,
    )

    @api.depends("product_id")
    def _compute_price(self):
        for line in self:
            if line.product_id:
                # Get the base price from the product
                base_price = line.product_id.lst_price
                
                # Calculate tax amount and add to get TTC price
                taxes = line.product_id.taxes_id.filtered(
                    lambda t: t.company_id == line.company_id
                )
                
                if taxes:
                    # Calculate the total tax rate
                    tax_rate = 0.0
                    for tax in taxes:
                        if tax.amount_type == 'percent':
                            tax_rate += tax.amount / 100.0
                        elif tax.amount_type == 'fixed':
                            # For fixed taxes, we'll add them to the base price
                            base_price += tax.amount
                    
                    # Apply tax rate to get TTC price
                    line.price = base_price * (1 + tax_rate)
                else:
                    # No taxes, use base price
                    line.price = base_price
            else:
                line.price = 0.0

    @api.depends("price", "quantity")
    def _compute_total(self):
        for line in self:
            line.total = line.price * line.quantity
