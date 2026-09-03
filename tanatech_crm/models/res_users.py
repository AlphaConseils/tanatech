# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    only_authorized_pipeline = fields.Boolean(
        string="Only authorized pipelines", default=False
    )
    user_id = fields.Many2many(
        "res.users", "res_users_rel", "res_user_id", "user_id", string="Authorized"
    )

    def _get_invalidation_fields(self):
        # The CRM record rule ``crm_only_authorized_pipeline_rule`` reads these
        # two fields through ``user`` and Odoo caches the evaluated domain, so
        # the cache must be dropped when they change. Previously every write on
        # res.users cleared the whole ORM cache of every worker.
        return super()._get_invalidation_fields() | {
            "only_authorized_pipeline",
            "user_id",
        }
