# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class SanctionType(models.TransientModel):
    """
    Choose sanction type
    """

    _name = "sanction.type.wizard"
    _description = "Choose sanction type with diffrents options"

    sanction_type_id = fields.Many2one(comodel_name="sanction.type")
    demex_date = fields.Date()
    sanction_date = fields.Date("Sanction date")
    precursor_fact = fields.Char(required=False)

    is_long_duration = fields.Boolean("Is long duration ?")

    sanction_start_date = fields.Date("Sanction start date")
    sanction_end_date = fields.Date("Sanction end date", )
    sanction_duration = fields.Float("Duration (days)", compute="_compute_sanction_duration")

    # TODO : take into account excluding weekend from the computation if it gets included in the interval date
    @api.depends('sanction_start_date', 'sanction_end_date')
    def _compute_sanction_duration(self):
        for rec in self:
            if rec.sanction_start_date and rec.sanction_end_date:
                duration = (rec.sanction_end_date - rec.sanction_start_date).days
                if duration < 0:
                    raise UserError("Incorrect sanction interval date !")
                rec.sanction_duration = float(duration)
            elif rec.sanction_start_date and not rec.sanction_end_date:
                rec.sanction_duration = float(1)
            else:
                rec.sanction_duration = 0.0

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
                "is_long_duration",
                "sanction_start_date",
                "sanction_end_date",
                "sanction_duration",
            ]
        )
        if sanction and is_fields_exist:
            defaults["demex_date"] = sanction.demex_date
            defaults["sanction_type_id"] = sanction.sanction_type_id
            defaults["sanction_date"] = sanction.sanction_date
            defaults["precursor_fact"] = sanction.precursor_fact
            defaults["is_long_duration"] = sanction.is_long_duration
            defaults["sanction_start_date"] = sanction.sanction_start_date
            defaults["sanction_end_date"] = sanction.sanction_end_date
            defaults["sanction_duration"] = sanction.sanction_duration
        return defaults

    def action_save_sanction(self):
        """
        Save user sanction
        """
        sanction = (
            self.sudo().env["sanction.sanction"].browse(self.env.context["active_id"])
        )
        if not self.is_long_duration and not self.sanction_date:
            raise ValidationError(_("Sanction date is required !"))
        if self.is_long_duration and (not self.sanction_start_date or not self.sanction_end_date):
            raise ValidationError(_("Sanction interval date is required for long lasting sanction ! (start date and end date must be specified)"))
        sanction.sanction_type_id = self.sanction_type_id.id
        sanction.sanction_date = self.sanction_date
        sanction.precursor_fact = self.precursor_fact
        sanction.is_long_duration = self.is_long_duration
        sanction.sanction_start_date = self.sanction_start_date
        sanction.sanction_end_date = self.sanction_end_date
        sanction.sanction_duration = self.sanction_duration if self.is_long_duration else 1
        sanction.demex_date = (
            self.demex_date if not sanction.demex_date else sanction.demex_date
        )
