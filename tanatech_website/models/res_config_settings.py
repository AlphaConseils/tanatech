# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'


    background = fields.Selection(selection=[('color', 'Color Picker'),
                                             ('image', 'Image'),
                                             ('url', 'URL')],
                                  string="Background",
                                  help="Background of the login page",
                                  config_parameter="tanatech_website.background")
    image = fields.Binary(string="Image", help="Select background image "
                                               "of login page")
    url = fields.Char(string="URL", help="Select and url of image",
                      config_parameter="tanatech_website.url")
    color = fields.Char(string="Color", help="Set a colour for background "
                                             "of login page",
                        config_parameter="tanatech_website.color")

    @api.model
    def get_values(self):
        """Super the get_values function to get the field values."""
        res = super(ResConfigSettings, self).get_values()
        params = self.env['ir.config_parameter'].sudo()
        res.update(image=params.get_param('tanatech_website.image'))
        return res

    def set_values(self):
        """Super the set_values function to save the field values."""
        super(ResConfigSettings, self).set_values()
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('tanatech_website.image', self.image)

    
