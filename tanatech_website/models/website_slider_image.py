from odoo import models, fields


class SliderImage(models.Model):
    _name = "website.slider.image"

    active = fields.Boolean(
        default=True,
    )
    title = fields.Char(required=True)
    image = fields.Image()
    website_published = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    note = fields.Text(translate=True)
    website_id = fields.Many2one("website", required=True)
