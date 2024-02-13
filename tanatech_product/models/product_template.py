# -*- coding: utf-8 -*-

from odoo import api, models, _, fields, exceptions
from odoo.exceptions import AccessDenied


class ProductTemplate(models.Model):
    _inherit = "product.template"
    _description = "Description"

    is_product_service_charge = fields.Boolean()
    percentage_service_charge = fields.Float(default=0.07)
    editable = fields.Boolean(default=True)

    @api.constrains("is_product_service_charge")
    def check_is_product_service_charge(self):
        checked_product_service_charge = self.search(
            [("id", "!=", self.id), ("is_product_service_charge", "=", True)], limit=1
        )
        if self.is_product_service_charge and checked_product_service_charge:
            raise exceptions.ValidationError(
                _("Il y a dejat un produit de service installation")
            )

    def get_price_unit_tax_incl(self):
        self.ensure_one()
        price = self.list_price
        res = self.taxes_id.compute_all(
            price, product=self, partner=self.env["res.partner"]
        )
        return res["total_included"]

    def write(self, vals):
        res = super().write(vals)
        if any(not product_id.editable for product_id in self):
            raise AccessDenied(
                _(
                    "The requested operation cannot be completed due to security restrictions.(Write Product)."
                )
            )
        return res
