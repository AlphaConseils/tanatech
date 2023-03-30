# -*- coding: utf-8 -*-

from odoo import models, fields, api

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    user_ids = fields.Many2many(comodel_name='res.users', string='Allowed users')

    @api.model
    def create(self, vals):
        self.clear_caches()
        return super(AccountJournal, self).create(vals)

    def write(self, vals):
        self.clear_caches()
        return super(AccountJournal, self).write(vals)

class ResUsers(models.Model):
    _inherit = 'res.users'

    @api.model
    def get_allowed_journal(self):
        return self.env['account.journal'].search([]).filtered(lambda journal_id: not journal_id.user_ids or self.id in journal_id.user_ids.ids).ids