# -*- coding: utf-8 -*-

# Klystron Global LLC
# Copyright (C) Klystron Global LLC
# All Rights Reserved
# https://www.klystronglobal.com/


from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    hide_menu_access_ids = fields.Many2many('ir.ui.menu', 'ir_ui_hide_menu_rel', 'uid', 'menu_id',
                                            string='Hide Access Menu')

    def _get_invalidation_fields(self):
        # The visible menus of a user are cached (see ir_module.py); only a
        # change of the hidden menus needs to drop that cache. The previous
        # override cleared the whole ORM cache on every write of any field.
        return super()._get_invalidation_fields() | {'hide_menu_access_ids'}
