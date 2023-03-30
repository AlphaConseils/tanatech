# -*- coding: utf-8 -*-

from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    journal_id = fields.Many2one(required=False, default=False)

    @api.constrains('move_type', 'journal_id')
    def _check_journal_type(self):
        """ DELETE JOURNAL CONSTRAINT *** LEAVE ME ALONE. """
        pass