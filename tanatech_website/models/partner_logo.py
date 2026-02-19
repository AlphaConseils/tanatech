from odoo import models, fields


class PartnerLogo(models.Model):
    _name = 'partner.logo'
    _description = 'Logo'

    name = fields.Char("Nom du partenaire")
    image = fields.Image("Logo")
    website_published = fields.Boolean("Publié sur le site", default=True)
