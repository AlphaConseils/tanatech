# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, _

class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    def activity_update(self):
        return