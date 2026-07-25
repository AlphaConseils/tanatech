# Part of Odoo. See LICENSE file for full copyright and licensing details.
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """ Resync the stored field hr_payslip.is_from_undeclared_contract with the
    restored compute (True when the contract or the structure is not_declared).

    The 552f225 regression forced the compute to False, so every payslip
    (re)computed since then is stored wrong. Pure SQL, idempotent, and it only
    touches this one column: amounts, lines and states are never read nor
    written. A second run updates 0 rows.
    """
    cr.execute(
        """
        UPDATE hr_payslip p
           SET is_from_undeclared_contract = sub.expected
          FROM (
                SELECT p2.id,
                       (COALESCE(c.contract_category = 'not_declared', FALSE)
                        OR COALESCE(t.structure_category = 'not_declared', FALSE)
                       ) AS expected
                  FROM hr_payslip p2
             LEFT JOIN hr_contract c ON c.id = p2.contract_id
             LEFT JOIN hr_payroll_structure s ON s.id = p2.struct_id
             LEFT JOIN hr_payroll_structure_type t ON t.id = s.type_id
               ) sub
         WHERE sub.id = p.id
           AND p.is_from_undeclared_contract IS DISTINCT FROM sub.expected
        """
    )
    _logger.info(
        "is_from_undeclared_contract recomputé sur %s fiche(s) de paie",
        cr.rowcount,
    )
