from odoo import models, fields, api

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    is_fana = fields.Boolean(string='FA-NA', store=True)