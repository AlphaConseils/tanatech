# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """ Realign the stored ``is_declared_type`` on payroll structures with the
    category of their structure type.

    ``is_declared_type`` only recomputed on ``type_id`` change (not when the type's
    ``structure_category`` was edited afterwards). Structures whose type was switched
    to "Undeclared" therefore kept a stale ``True`` value, which made NA payslips be
    treated as declared and caused salary adjustments to be imputed twice. """
    env = api.Environment(cr, SUPERUSER_ID, {})
    structures = env['hr.payroll.structure'].with_context(active_test=False).search([])
    for structure in structures:
        is_declared = structure.type_id.structure_category == 'declared'
        if structure.is_declared_type != is_declared:
            structure.is_declared_type = is_declared
