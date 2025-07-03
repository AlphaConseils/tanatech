# -*- coding: utf-8 -*-
from odoo import models, fields, api


class SanctionType(models.TransientModel):
    """
    Choose sanction type
    """

    _name = "sanction.type.wizard"
    _description = "Choose sanction type with diffrents options"

    sanction_type_id = fields.Many2one(comodel_name="sanction.type")
    demex_date = fields.Date()
    sanction_date = fields.Date("Sanction date", default=fields.Date.today())
    precursor_fact = fields.Char(required=False)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        sanction = (
            self.sudo().env["sanction.sanction"].browse(self.env.context["active_id"])
        )
        is_fields_exist = all(
            field in fields_list
            for field in [
                "demex_date",
                "sanction_type_id",
                "sanction_date",
                "precursor_fact",
            ]
        )
        if sanction and is_fields_exist:
            defaults["demex_date"] = sanction.demex_date
            defaults["sanction_type_id"] = sanction.sanction_type_id
            defaults["sanction_date"] = sanction.sanction_date
            defaults["precursor_fact"] = sanction.precursor_fact
        return defaults

    def action_save_sanction(self):
        """
        Save user sanction
        """
        sanction = (
            self.sudo().env["sanction.sanction"].browse(self.env.context["active_id"])
        )
        sanction.sanction_type_id = self.sanction_type_id.id
        sanction.sanction_date = self.sanction_date
        sanction.precursor_fact = self.precursor_fact
        sanction.demex_date = (
            self.demex_date if not sanction.demex_date else sanction.demex_date
        )
