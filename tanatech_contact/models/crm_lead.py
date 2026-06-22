# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class Lead(models.Model):
    _inherit = "crm.lead"
    _description = "Lead/Opportunity"

    client_code = fields.Many2one(
        "res.partner",
        string="Client Code",
        help="Sélectionnez le client par son code",
    )

    @api.onchange("client_code")
    def _onchange_client_code(self):
        if self.client_code:
            self.partner_id = self.client_code

            if self.client_code.email:
                self.email_from = self.client_code.email
            if self.client_code.phone:
                self.phone = self.client_code.phone
