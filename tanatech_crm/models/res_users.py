# -*- coding: utf-8 -*-

from odoo import models,api,fields
import pytz
import datetime

class ResUsers(models.Model):
    _inherit = 'res.users'

    only_authorized_pipeline = fields.Boolean(string="Only authorized pipelines",default=False)
    user_id = fields.Many2many('res.users','res_users_rel','res_user_id','user_id',string="Authorized")

    @api.model_create_multi
    def create(self, vals_list):
        self.clear_caches()
        return super(ResUsers,self).create(vals_list)

    def write(self, vals):
        self.clear_caches()
        return super(ResUsers,self).write(vals)

    @api.depends('tz')
    def _compute_tz_offset(self):
        for user in self:
            user.tz_offset = datetime.datetime.now(pytz.timezone('GMT')).strftime('%z')
