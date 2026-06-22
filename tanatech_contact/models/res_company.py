# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class ResCompany(models.Model):
    _inherit = "res.company"

    # Explicit prefix mapping per company name. Add new entries here
    # whenever a new company is created.
    _CLIENT_CODE_PREFIXES = {
        "TANATECH": "TAN",
        "MASONTSIKA": "MAS",
        "STUDYDAS": "STD",
    }

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        for company in companies:
            company._ensure_client_code_sequence()
        return companies

    def _ensure_client_code_sequence(self):
        """Make sure each company has its own client code sequence,
        with a distinct prefix to avoid collisions on the unique
        client_code constraint across companies."""
        self.ensure_one()
        Sequence = self.env["ir.sequence"].sudo()
        existing = Sequence.search(
            [
                ("code", "=", "res.partner.client.code"),
                ("company_id", "=", self.id),
            ],
            limit=1,
        )
        if existing:
            return existing

        return Sequence.create(
            {
                "name": _("Client Code Sequence - %s") % self.name,
                "code": "res.partner.client.code",
                "prefix": self._get_client_code_prefix(),
                "padding": 5,
                "number_next": 1,
                "number_increment": 1,
                "company_id": self.id,
            }
        )

    def _get_client_code_prefix(self):
        """Return the explicit prefix for known companies, falling back
        to a generic prefix derived from the company name if unknown."""
        self.ensure_one()
        if self.name in self._CLIENT_CODE_PREFIXES:
            return self._CLIENT_CODE_PREFIXES[self.name]

        # Fallback for any future company not listed above
        initials = "".join(word[0] for word in self.name.split()[:3]).upper()
        return f"CL-{initials}-"
