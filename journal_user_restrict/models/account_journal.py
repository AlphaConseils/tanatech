# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    user_ids = fields.Many2many(comodel_name='res.users', string='Allowed users')

    @api.model_create_multi
    def create(self, vals_list):
        self.clear_caches()
        return super(AccountJournal, self).create(vals_list)

    def write(self, vals):
        self.clear_caches()
        return super(AccountJournal, self).write(vals)

