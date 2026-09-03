# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestResUsersCache(TransactionCase):
    def test_pipeline_fields_drop_the_cache_and_signature_does_not(self):
        Users = self.env["res.users"]
        invalidation_fields = Users._get_invalidation_fields()
        self.assertIn("only_authorized_pipeline", invalidation_fields)
        self.assertIn("user_id", invalidation_fields)
        self.assertNotIn("signature", invalidation_fields)

    def test_rule_domain_follows_authorized_users(self):
        group_user = self.env.ref("base.group_user")
        sales_group = self.env.ref("sales_team.group_sale_salesman")
        owner, colleague = self.env["res.users"].create(
            [
                {
                    "name": "Pipeline owner",
                    "login": "pipeline_owner",
                    "groups_id": [(6, 0, (group_user | sales_group).ids)],
                    "only_authorized_pipeline": True,
                },
                {
                    "name": "Pipeline colleague",
                    "login": "pipeline_colleague",
                    "groups_id": [(6, 0, (group_user | sales_group).ids)],
                },
            ]
        )
        Rule = self.env["ir.rule"]
        before = Rule.with_user(owner)._compute_domain("crm.lead", "read")
        owner.write({"user_id": [(6, 0, colleague.ids)]})
        after = Rule.with_user(owner)._compute_domain("crm.lead", "read")
        self.assertNotEqual(
            before, after, "the cached rule domain must follow the authorized users"
        )
