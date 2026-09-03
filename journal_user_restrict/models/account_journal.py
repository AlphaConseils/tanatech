# -*- coding: utf-8 -*-

from odoo import api, fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    user_ids = fields.Many2many(comodel_name='res.users', string='Allowed users')

    @api.model_create_multi
    def create(self, vals_list):
        journals = super().create(vals_list)
        if any(vals.get('user_ids') for vals in vals_list):
            self._clear_allowed_journal_cache()
        return journals

    def write(self, vals):
        res = super().write(vals)
        if 'user_ids' in vals:
            self._clear_allowed_journal_cache()
        return res

    def _clear_allowed_journal_cache(self):
        # The record rules of this module embed ``user.get_allowed_journal()``
        # in their cached domain, so the rule cache must be refreshed when the
        # allowed users change. Any other write on a journal leaves the cache
        # alone (the previous overrides cleared it on every write).
        self.env.registry.clear_cache()


class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def get_allowed_journal(self):
        return self.env['account.journal'].search([]).filtered(lambda journal_id: not journal_id.user_ids or self.id in journal_id.user_ids.ids).ids
