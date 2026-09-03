# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHideMenu(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref("base.group_user")
        cls.user_hidden, cls.user_full = cls.env["res.users"].create(
            [
                {
                    "name": "Hidden menus",
                    "login": "kg_hidden",
                    "groups_id": [(6, 0, group_user.ids)],
                },
                {
                    "name": "All menus",
                    "login": "kg_full",
                    "groups_id": [(6, 0, group_user.ids)],
                },
            ]
        )
        # Hide a menu that a plain internal user can normally see.
        visible_menu_ids = (
            cls.env["ir.ui.menu"].with_user(cls.user_full)._visible_menu_ids(debug=False)
        )
        cls.menu = cls.env["ir.ui.menu"].browse(min(visible_menu_ids))
        cls.user_hidden.hide_menu_access_ids = [(6, 0, cls.menu.ids)]

    def _visible_menus(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids(debug=False)

    def test_hidden_menu_is_only_hidden_for_its_user(self):
        # Same groups on both users: the cache key must still tell them apart,
        # whichever one loads its menus first.
        self.assertNotIn(self.menu.id, self._visible_menus(self.user_hidden))
        self.assertIn(self.menu.id, self._visible_menus(self.user_full))
        self.assertNotIn(self.menu.id, self._visible_menus(self.user_hidden))

    def test_changing_hidden_menus_refreshes_visible_menus(self):
        self.assertNotIn(self.menu.id, self._visible_menus(self.user_hidden))
        self.user_hidden.hide_menu_access_ids = [(5, 0, 0)]
        self.assertIn(self.menu.id, self._visible_menus(self.user_hidden))

    def test_hidden_menus_field_invalidates_cache_and_others_do_not(self):
        invalidation_fields = self.env["res.users"]._get_invalidation_fields()
        self.assertIn("hide_menu_access_ids", invalidation_fields)
        self.assertNotIn("signature", invalidation_fields)
