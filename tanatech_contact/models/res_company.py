# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


_DEFAULT_CLIENT_CODE_PREFIXES = {
        "TANATECH": "TAN",
        "MASONTSIKA": "MAS",
        "STUDYDAS": "STD",
    }

class ResCompany(models.Model):
    _inherit = "res.company"

    prefix_sequence = fields.Char(
        string="Préfixe Code Client",
        help="Préfixe utilisé pour générer le Code Client (client_code) "
             "des contacts rattachés à cette société. Ex: TAN, MAS, STD.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            company._ensure_client_code_sequence()
        return companies

    def write(self, vals):
        res = super().write(vals)
        if "prefix_sequence" in vals:
            for company in self:
                company._sync_client_code_sequence_prefix()
        return res

    def _ensure_client_code_sequence(self):
        """Make sure each company has its own client code sequence,
        using prefix_sequence (falls back to a generated value if empty).
        Idempotent: always re-checks for an existing sequence right
        before creating, to avoid duplicates from concurrent calls."""
        self.ensure_one()
        Sequence = self.env["ir.sequence"].sudo()

        if not self.prefix_sequence:
            self.prefix_sequence = self._get_default_prefix_sequence()

        # Search ALL matches, not just limit=1, so we can detect and
        # clean up duplicates if they already exist.
        existing = Sequence.search(
            [
                ("code", "=", "res.partner.client.code"),
                ("company_id", "=", self.id),
            ],
            order="id asc",
        )

        if existing:
            keep = existing[0]
            duplicates = existing[1:]
            if duplicates:
                # Keep the oldest (likely the one already in use with
                # the highest number_next), remove the rest.
                duplicates.unlink()
            if keep.prefix != self.prefix_sequence:
                keep.prefix = self.prefix_sequence
            return keep

        return Sequence.create(
            {
                "name": _("Client Code Sequence - %s") % self.name,
                "code": "res.partner.client.code",
                "prefix": self.prefix_sequence,
                "padding": 5,
                "number_next": 1,
                "number_increment": 1,
                "company_id": self.id,
            }
        )

    def _sync_client_code_sequence_prefix(self):
        """Keep the ir.sequence prefix in sync whenever prefix_sequence
        is edited by the user on the company form."""
        self.ensure_one()
        sequence = self.env["ir.sequence"].sudo().search(
            [
                ("code", "=", "res.partner.client.code"),
                ("company_id", "=", self.id),
            ],
            limit=1,
        )
        if sequence:
            sequence.prefix = self.prefix_sequence or ""
        else:
            self._ensure_client_code_sequence()

    def _get_default_prefix_sequence(self):
        """Return the explicit prefix for known companies, falling back
        to a generic prefix derived from the company name if unknown."""
        self.ensure_one()
        if self.name in self._DEFAULT_CLIENT_CODE_PREFIXES:
            return self._DEFAULT_CLIENT_CODE_PREFIXES[self.name]

        initials = "".join(word[0] for word in self.name.split()[:3]).upper()
        return initials

    @api.model
    def _backfill_client_code_sequences(self):
        """Ensure every existing company has its client code sequence."""
        for company in self.search([]):
            company._ensure_client_code_sequence()