# -*- coding: utf-8 -*-

# Klystron Global LLC
# Copyright (C) Klystron Global LLC
# All Rights Reserved
# https://www.klystronglobal.com/


from odoo import models, api, tools


class Menu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    @tools.ormcache('self.env.uid', 'frozenset(self.env.user.groups_id.ids)', 'debug')
    def _visible_menu_ids(self, debug=False):
        # The result depends on the current user (hide_menu_access_ids), so the
        # cache key must include the user: keyed on groups only, two users with
        # the same groups shared the hidden menus of whoever loaded them first.
        menus = super(Menu, self)._visible_menu_ids(debug)
        user = self.env.user
        if user.hide_menu_access_ids and not user.has_group('base.group_system'):
            menus = set(menus) - set(user.hide_menu_access_ids.ids)
        return menus
