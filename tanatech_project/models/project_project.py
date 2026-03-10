from odoo import models, fields


class Project(models.Model):
    _inherit = "project.project"

    hide_partner = fields.Boolean(string="Hide Customer Field")
