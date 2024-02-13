from odoo import models, fields, api, exceptions

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    allow_edit = fields.Boolean(string="Autoriser la modification de l'article")

    def write(self, vals):
        if not self.allow_edit:
            raise exceptions.UserError("La modification de l'article est désactivée.")
        return super(ProductTemplate, self).write(vals)
