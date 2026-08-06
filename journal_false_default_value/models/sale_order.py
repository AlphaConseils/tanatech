from odoo import api, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            if order.website_id:
                journal = self.env["account.journal"].search(
                    [
                        ("code", "=", "FA-NA"),
                        ("type", "=", "sale"),
                    ],
                    limit=1,
                )
                if journal:
                    order.journal_id = journal
        return orders

    def _prepare_invoice(self):
        vals = {**super()._prepare_invoice(), "journal_id": False}
        if self.website_id:
            journal = self.env["account.journal"].search(
                [
                    ("code", "=", "FA-NA"),
                    ("type", "=", "sale"),
                    ("company_id", "=", self.company_id.id),
                ],
                limit=1,
            )
            if journal:
                vals["journal_id"] = journal.id
        return vals
