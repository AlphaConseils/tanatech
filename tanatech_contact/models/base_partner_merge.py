# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class BasePartnerMergeAutomaticWizard(models.TransientModel):
    _inherit = "base.partner.merge.automatic.wizard"

    def _merge(self, partner_ids, dst_partner=None, extra_checks=True):
        Partner = self.env["res.partner"]
        partners = Partner.browse(partner_ids).exists()
        # Capture existing codes before merge, since they will be lost after unlink
        old_codes = partners.mapped("client_code")

        res = super(
            BasePartnerMergeAutomaticWizard,
            self.with_context(skip_client_code_company_sync=True),
        )._merge(partner_ids, dst_partner=dst_partner, extra_checks=extra_checks)

        if dst_partner and dst_partner.exists():
            if not dst_partner.client_code:
                # Ensure the surviving partner always has a client code
                # after merge, using its own company's sequence/prefix
                dst_partner.client_code = self.env[
                    "res.partner"
                ]._get_next_sequence_client_code(dst_partner.company_id.id or False)
            self._resequence_client_codes(old_codes, dst_partner)

        return res

    def _resequence_client_codes(self, old_codes, dst_partner):
        """Fill the gap(s) left by the merge by shifting down
        all higher client codes by one, scoped to dst_partner's company
        sequence (codes use that company's prefix)."""
        Partner = self.env["res.partner"]
        company_id = dst_partner.company_id.id or False
        sequence = Partner._get_sequence_for_company(company_id)
        if not sequence:
            return

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0

        def code_to_number(code):
            # Extract the numeric part of a client code, ignoring the prefix
            if not code or not code.startswith(prefix):
                return None
            num_part = code[len(prefix) :]
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

        domain = [("client_code", "!=", False)]
        domain += (
            [("company_id", "=", company_id)]
            if company_id
            else [("company_id", "=", False)]
        )
        all_partners = Partner.sudo().search(domain, order="client_code asc")

        # Compute (partner, new_code) pairs first, without writing yet
        to_update = []
        for partner in all_partners:
            num = code_to_number(partner.client_code)
            if num is None:
                continue
            shift = sum(1 for f in freed_numbers if f < num)
            if shift:
                new_num = num - shift
                new_code = f"{prefix}{str(new_num).zfill(padding)}"
                if new_code != partner.client_code:
                    to_update.append((partner, new_code))

        if to_update:
            # Phase 1: move all affected partners to unique temporary
            # placeholders, to avoid mid-statement unique constraint
            # collisions when codes are shifted in a single batched UPDATE.
            for partner, _new_code in to_update:
                partner.with_context(skip_client_code_company_sync=True).client_code = (
                    f"__TMP__{partner.id}"
                )

            # Phase 2: assign the real, final codes
            for partner, new_code in to_update:
                partner.with_context(skip_client_code_company_sync=True).client_code = (
                    new_code
                )

        # Reset the sequence so the next generated code continues logically
        all_partners = Partner.sudo().search(domain)
        computed_numbers = [
            n
            for n in (code_to_number(p.client_code) for p in all_partners)
            if n is not None
        ]
        max_number = max(computed_numbers, default=0)
        sequence.number_next = max_number + 1
