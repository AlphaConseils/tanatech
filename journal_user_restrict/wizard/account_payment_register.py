from odoo import models, api


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.model
    def _get_batch_available_journals(self, batch_result):
        uid = self.env.user.id
        journals = super()._get_batch_available_journals(batch_result)
        return journals.filtered(lambda journal: not journal.user_ids or uid in journal.user_ids.ids)