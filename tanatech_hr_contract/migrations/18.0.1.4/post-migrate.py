# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """ Rename the NA mirror contracts from the legacy "N.D." suffix to "NA".

    Ships with the code change that generates the suffix (hr_contract.py):
    both must land in the same module version, otherwise any later rename of
    a declared contract would regenerate the "N.D." suffix on its mirror.

    Plain SQL on hr_contract: covers active AND archived contracts, and is
    idempotent (once no name contains ' - N.D.' anymore, both updates hit
    zero rows).
    """
    # 1) Doubled suffixes first (one known case: "PE DECLARE - N.D. - N.D.").
    #    Running the generic REPLACE alone would turn them into "... - NA - NA",
    #    so the doubled pattern is collapsed to a single " - NA" beforehand.
    cr.execute("""
        UPDATE hr_contract
           SET name = REPLACE(name, ' - N.D. - N.D.', ' - NA')
         WHERE name LIKE '%% - N.D. - N.D.%%'
    """)
    doubled = cr.rowcount

    # 2) Generic rename of the remaining legacy suffixes.
    cr.execute("""
        UPDATE hr_contract
           SET name = REPLACE(name, ' - N.D.', ' - NA')
         WHERE name LIKE '%% - N.D.%%'
    """)
    renamed = cr.rowcount

    _logger.info(
        "ND->NA contract rename: %s doubled suffix(es) collapsed, "
        "%s contract name(s) renamed.", doubled, renamed,
    )

    # Safety net: report any leftover N.D. marker (unexpected variants).
    cr.execute("SELECT id, name FROM hr_contract WHERE name LIKE '%%N.D.%%'")
    leftovers = cr.fetchall()
    if leftovers:
        _logger.warning(
            "ND->NA contract rename: %s contract(s) still carry an 'N.D.' "
            "marker and need a manual check: %s", len(leftovers), leftovers,
        )
