# -*- coding: utf-8 -*-
from num2words import num2words
from odoo import models, fields


class AccountMove(models.Model):
    _inherit = "account.move"

    related_journal = fields.Char(related='journal_id.name', string='Journal Name', readonly=True)

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

    def amount_to_words(self, amount):
        """
        Convert amount to text with proper formatting for dollars and cents in French,
        starting with a majuscule.
        """
        integer_part = int(amount)
        decimal_part = int(round((amount - integer_part) * 100))
        integer_in_words = num2words(integer_part, lang="fr")
        if decimal_part > 0:
            decimal_in_words = num2words(decimal_part, lang="fr")
            result = f" {integer_in_words}  {decimal_in_words} {self.currency_id.currency_unit_label if self.currency_id else 'Ariary'}"
        else:
            result = f" {integer_in_words} {self.currency_id.currency_unit_label if self.currency_id else 'Ariary'}"
        result = result[0].upper() + result[1:]

        return result

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    price_unit_ht = fields.Float(string="Prix", compute="_compute_price_unit_ht")

    def _compute_price_unit_ht(self):
        for rec in self:
            rec.price_unit_ht = (rec.price_total if rec.price_total else 1) / (rec.quantity if rec.quantity else 1)