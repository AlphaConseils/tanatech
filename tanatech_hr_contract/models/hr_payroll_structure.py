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
