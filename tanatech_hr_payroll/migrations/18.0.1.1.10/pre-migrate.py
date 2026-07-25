# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Protège les deux actions serveur d'impression AVANT que le rechargement des
# données du module (data/ir_actions_server.xml) ne s'exécute pour cette montée
# de version.
#
# Ces actions ont pu être créées à la main en base (impression depuis la vue
# liste) avant d'être codifiées en XML. Sans external ID protégé, le rechargement
# du fichier data lors de l'upgrade risque de dupliquer l'action ou d'écraser une
# personnalisation. Ce script, exécuté en pre-migrate, garantit qu'il existe une
# entrée ir.model.data (dans notre namespace) marquée noupdate=True pour chacune :
#   - présente            -> on force noupdate=True ;
#   - absente mais action  -> on crée l'external ID (noupdate=True) qui pointe
#     serveur existante       sur l'action déjà en base, pour que le XML la mette
#                             à jour au lieu d'en créer une seconde.
# Idempotent : une seconde exécution ne modifie plus rien.

_MODULE = "tanatech_hr_payroll"
_MODEL = "ir.actions.server"
_PAYSLIP_MODEL = "hr.payslip"

# external ID (name dans ir.model.data) -> nom exact de l'action serveur en base.
_ACTIONS = [
    ("action_server_print_payslips", "Imprimer les bulletins (A4)"),
    ("action_server_print_nd_tickets", "Imprimer les tickets (NA)"),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Imd = env["ir.model.data"]

    for xmlid_name, action_name in _ACTIONS:
        imd = Imd.search([
            ("module", "=", _MODULE),
            ("name", "=", xmlid_name),
            ("model", "=", _MODEL),
        ], limit=1)

        if imd:
            if imd.noupdate:
                _logger.info(
                    "IR_ACTIONS_SERVER : '%s.%s' déjà protégée (noupdate=True).",
                    _MODULE, xmlid_name,
                )
            else:
                imd.noupdate = True
                _logger.info(
                    "IR_ACTIONS_SERVER : '%s.%s' protégée (noupdate passé à True).",
                    _MODULE, xmlid_name,
                )
            continue

        # Pas d'external ID : on tente de retrouver l'action serveur par son nom,
        # restreint au modèle hr.payslip pour éviter tout homonyme.
        action = env[_MODEL].search([
            ("name", "=", action_name),
            ("model_id.model", "=", _PAYSLIP_MODEL),
        ])
        if not action:
            _logger.warning(
                "IR_ACTIONS_SERVER : ni external ID '%s.%s' ni action serveur "
                "'%s' (sur %s) trouvés — le fichier data la (re)créera.",
                _MODULE, xmlid_name, action_name, _PAYSLIP_MODEL,
            )
            continue
        if len(action) > 1:
            _logger.warning(
                "IR_ACTIONS_SERVER : %s actions nommées '%s' sur %s — "
                "external ID '%s.%s' non créé (désambiguïsation manuelle requise).",
                len(action), action_name, _PAYSLIP_MODEL, _MODULE, xmlid_name,
            )
            continue

        Imd.create({
            "module": _MODULE,
            "name": xmlid_name,
            "model": _MODEL,
            "res_id": action.id,
            "noupdate": True,
        })
        _logger.info(
            "IR_ACTIONS_SERVER : external ID '%s.%s' créé (noupdate=True) "
            "vers l'action serveur '%s' (id %s).",
            _MODULE, xmlid_name, action_name, action.id,
        )
