# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    # Read by the record rules of this module through a sub-query at each
    # evaluation: no cache depends on it, so no cache clearing is needed on
    # create/write (the previous overrides cleared the whole ORM cache).
    user_ids = fields.Many2many(comodel_name='res.users', string='Allowed users')
