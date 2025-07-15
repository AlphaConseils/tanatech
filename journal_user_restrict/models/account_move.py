# -*- coding: utf-8 -*-

from odoo import models

class AccountMove(models.Model):
    _inherit = "account.move"

    def _search_default_journal(self):
        """Filtered journal by user"""
        return (
            super()
            ._search_default_journal()
            .filtered(
                lambda journal: not journal.user_ids
                or self.env.user.id in journal.user_ids.ids
            )
        )
