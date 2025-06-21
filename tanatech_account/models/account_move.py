# -*- coding: utf-8 -*-

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_reconciled_info_JSON_values(self):
        self.ensure_one()
        reconciled_vals = []
        invoice_partials, exchange_diff_moves = self._get_reconciled_invoices_partials()

        for (
            partial,
            amount,
            counterpart_line,
        ) in invoice_partials:
            reconciled_vals.append(
                self._get_reconciled_vals(partial, amount, counterpart_line)
            )
        return reconciled_vals

    def _get_reconciled_vals(self, partial, amount, counterpart_line):
        if counterpart_line.move_id.ref:
            reconciliation_ref = "%s (%s)" % (
                counterpart_line.move_id.name,
                counterpart_line.move_id.ref,
            )
        else:
            reconciliation_ref = counterpart_line.move_id.name
        return {
            "name": counterpart_line.name,
            "journal_name": counterpart_line.journal_id.name,
            "amount": amount,
            "currency": self.currency_id.symbol,
            "digits": [69, self.currency_id.decimal_places],
            "position": self.currency_id.position,
            "date": counterpart_line.date,
            "payment_id": counterpart_line.id,
            "partial_id": partial.id,
            "account_payment_id": counterpart_line.payment_id.id,
            "payment_method_name": counterpart_line.payment_id.payment_method_line_id.name,
            "move_id": counterpart_line.move_id.id,
            "ref": reconciliation_ref,
        }
