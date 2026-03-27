from odoo import models, fields


class ProjectTask(models.Model):
    _inherit = "project.task"

    hide_partner = fields.Boolean(
        related="project_id.hide_partner",
        string="Hide Customer Field",
        store=True,
        required=False,
    )
