# -*- coding: utf-8 -*-

from odoo import _, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_amount


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _get_specific_processing_values(self, processing_values):
        res = super()._get_specific_processing_values(processing_values)

        if self.provider_id.code == "mvola":
            res["mvola_data"] = {
                "mvola_url": self.provider_id.mvola_url,
                "access_token": self.provider_id.mvola_token,
                "merchant_phone": self.provider_id.mvola_phone,
                "partner_name": self.partner_id.name,
            }
            res["item_number"] = self.reference

        return res

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != "mvola" or len(tx) == 1:
            return tx

        reference = notification_data.get("item_number")
        tx = self.search(
            [("reference", "=", reference), ("provider_code", "=", "mvola")]
        )
        if not tx:
            raise ValidationError(
                _("Mvola: ")
                + _("No transaction found matching reference %s.", reference)
            )

        return tx
