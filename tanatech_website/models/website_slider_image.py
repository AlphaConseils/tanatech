from odoo import models, fields


class SliderImage(models.Model):
    _name = "website.slider.image"

    name = fields.Char(required=True)
    image = fields.Image()
    website_published = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    website_id = fields.Many2one("website", required=True)
