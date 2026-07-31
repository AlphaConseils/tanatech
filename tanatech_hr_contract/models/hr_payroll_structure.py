# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    is_declared_type = fields.Boolean('Is declared type ?', compute='_compute_type', store=True)

    na_structure_id = fields.Many2one(
        'hr.payroll.structure',
        string="Structure NA associée",
        help="Structure non déclarée (NA) jumelle de cette structure déclarée. "
             "Utilisée pour créer la fiche de paie NA miroir sur la bonne "
             "structure, sans deviner par nom ou par catégorie.",
    )
    is_stc = fields.Boolean(
        string="Solde de tout compte",
        help="Identifie les structures de solde de tout compte (déclarée et NA). "
             "Pilote le routage d'impression (rapport de solde de tout compte "
             "au lieu du bulletin standard ou du ticket NA 80mm).",
    )

    @api.depends('type_id', 'type_id.structure_category')
    def _compute_type(self):
        for structure in self:
            if structure.type_id.structure_category == 'declared':
                structure.is_declared_type = True
            else:
                structure.is_declared_type = False

    def _get_category_counterpart(self, category):
        """ Return the structure equivalent to ``self`` for the given contract
        category, e.g. the declared "Solde Tout Compte" maps to the undeclared
        "Solde Tout Compte - NA" and conversely.

        Counterparts are matched by name inclusion (the convention used for the
        STC structures: the NA name embeds the declared name). Returns an empty
        recordset when there is no counterpart.
        """
        self.ensure_one()
        if self.type_id.structure_category == category:
            return self
        candidates = self.search([('type_id.structure_category', '=', category)])
        return candidates.filtered(
            lambda s: self.name and s.name and (self.name in s.name or s.name in self.name)
        )[:1]
