# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class BasePartnerMergeAutomaticWizard(models.TransientModel):
    _inherit = "base.partner.merge.automatic.wizard"

    def _merge(self, partner_ids, dst_partner=None, extra_checks=True):
        Partner = self.env["res.partner"]
        partners = Partner.browse(partner_ids).exists()
        # Capture existing codes before merge, since they will be lost after unlink
        old_codes = partners.mapped("client_code")

        res = super()._merge(
            partner_ids, dst_partner=dst_partner, extra_checks=extra_checks
        )

        if dst_partner and dst_partner.exists():
            if not dst_partner.client_code:
                # Ensure the surviving partner always has a client code after merge
                dst_partner.client_code = (
                    self.env["ir.sequence"].next_by_code("res.partner.client.code")
                    or "/"
                )
            self._resequence_client_codes(old_codes, dst_partner)

        return res

    def _resequence_client_codes(self, old_codes, dst_partner):
        """ Fill the gap(s) left by the merge by shifting down
            all higher client codes by one. """
        sequence = self.env["ir.sequence"].search(
            [("code", "=", "res.partner.client.code")], limit=1
        )
        if not sequence:
            return

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0

        def code_to_number(code):
            # Extract the numeric part of a client code, ignoring the prefix
            if not code or not code.startswith(prefix):
                return None
            num_part = code[len(prefix):]
            return int(num_part) if num_part.isdigit() else None

        numbers = sorted(
            n for n in (code_to_number(c) for c in old_codes if c) if n is not None
        )
        if len(numbers) < 2:
            return  # nothing to compress, no duplicate numeric codes involved

        kept_number = code_to_number(dst_partner.client_code)
        freed_numbers = sorted(n for n in numbers if n != kept_number)
        if not freed_numbers:
            return

        all_partners = self.env["res.partner"].sudo().search(
            [("client_code", "!=", False)], order="client_code asc"
        )

        for partner in all_partners:
            num = code_to_number(partner.client_code)
            if num is None:
                continue
            # Count how many freed numbers are below this partner's number
            shift = sum(1 for f in freed_numbers if f < num)
            if shift:
                new_num = num - shift
                new_code = f"{prefix}{str(new_num).zfill(padding)}"
                if new_code != partner.client_code:
                    partner.client_code = new_code

        # Reset the sequence so the next generated code continues logically
        max_number = max(
            (code_to_number(p.client_code) for p in all_partners if p.client_code),
            default=0,
        )
        sequence.number_next = max_number + 1