# -*-coding: utf-8 -*-
from odoo import fields, models, exceptions, _, api

class ResUser(models.Model):
    _inherit = 'res.users'

    is_rh = fields.Boolean('Responsible RH')
    
    # rh_responsible = fields.Boolean('RH Responsible')
    
    # @api.constrains('rh_responsible')
    # def check_unique_rh_responsible(self):
    #     rh_responsible = self.env['res.users'].search_count([('rh_responsible', '=', True)])
    #     if rh_responsible > 1:
    #         raise exceptions.ValidationError(_('HR responsible already exist.'))
