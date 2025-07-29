# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class HrPayrollStructureType(models.Model):
    _inherit = 'hr.payroll.structure.type'

    structure_category = fields.Selection(
        selection=[
            ('declared', "Declared"),
            ('not_declared', "Undeclared"),
        ],
        string="Structure Category",
        default="declared",
        required=True
    )

    