# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Nouvelle règle d'ajustement : arrondit le net à payer au multiple de
# 5 000 Ar le plus proche (inférieur si le reste < 2500, supérieur sinon).
#
# Les structures de paie et la catégorie de règle AJUST n'existent qu'en base
# (créées via l'UI, sans external ID dans le code) : la règle est donc créée par
# ce script de migration plutôt qu'en data XML. Le script est idempotent et
# assigne un external ID, dans notre namespace, à la catégorie AJUST, aux 4
# structures et à chaque règle SALARR créée, pour permettre de les référencer et
# de rejouer les mises à jour futures.

_MODULE = "tanatech_hr_payroll"
_CATEGORY_CODE = "AJUST"
_CATEGORY_XMLID = "salary_rule_category_ajust"
_RULE_CODE = "SALARR"
_RULE_NAME = "Ajustement arrondi"
_RULE_SEQUENCE = 10900

# Nom exact de la structure -> suffixe partagé par ses external IDs
# (payroll_structure_<suffixe> pour la structure, salary_rule_salarr_<suffixe>
# pour sa règle). Les ids DB attendus (2, 3, 4, 7) ne servent que de repère au
# log ; la résolution se fait par nom exact pour rester robuste d'une base à
# l'autre.
_STRUCTURES = [
    ("Paie Régulière", "regular_sd"),      # id DB attendu : 2
    ("Paie Régulière NA", "regular_na"),   # id DB attendu : 3
    ("Solde Tout Compte", "stc_sd"),       # id DB attendu : 4
    ("Solde Tout Compte NA", "stc_na"),    # id DB attendu : 7
]

_AMOUNT_PYTHON_COMPUTE = (
    'to_pay = (categories.get("NET") or 0) + (categories.get("OPCOMP") or 0) + (categories.get("AJUST") or 0)\n'
    'target = ((int(round(to_pay)) + 2500) // 5000) * 5000\n'
    'result = target - to_pay'
)


def _ensure_external_id(env, name, model, res_id):
    """ Assigne, de façon idempotente, l'external ID ``tanatech_hr_payroll.<name>``
    à l'enregistrement (model, res_id).

    Ne crée l'``ir.model.data`` que s'il n'existe pas déjà dans notre namespace ;
    ne touche jamais aux xmlids d'autres modules (ex. ``hr_payroll.*``). """
    existing = env["ir.model.data"].search([
        ("module", "=", _MODULE),
        ("name", "=", name),
    ], limit=1)
    if existing:
        if existing.res_id != res_id:
            existing.res_id = res_id
            _logger.info(
                "SALARR : external ID '%s.%s' réaligné sur %s(%s).",
                _MODULE, name, model, res_id,
            )
        return
    env["ir.model.data"].create({
        "module": _MODULE,
        "name": name,
        "model": model,
        "res_id": res_id,
        "noupdate": True,
    })
    _logger.info(
        "SALARR : external ID '%s.%s' assigné à %s(%s).",
        _MODULE, name, model, res_id,
    )


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    category = env["hr.salary.rule.category"].search(
        [("code", "=", _CATEGORY_CODE)], limit=1
    )
    if not category:
        _logger.error(
            "SALARR : catégorie de règle '%s' introuvable, "
            "aucune règle d'arrondi créée.", _CATEGORY_CODE,
        )
        return

    # External ID de la catégorie AJUST (dans notre namespace).
    _ensure_external_id(env, _CATEGORY_XMLID, "hr.salary.rule.category", category.id)

    Rule = env["hr.salary.rule"]

    for struct_name, suffix in _STRUCTURES:
        structure = env["hr.payroll.structure"].with_context(active_test=False).search(
            [("name", "=", struct_name)]
        )
        if not structure:
            _logger.warning(
                "SALARR : structure de paie '%s' introuvable, règle ignorée.",
                struct_name,
            )
            continue
        if len(structure) > 1:
            _logger.warning(
                "SALARR : %s structures nommées '%s', règle ignorée "
                "(désambiguïsation manuelle requise).",
                len(structure), struct_name,
            )
            continue

        # External ID de la structure (dans notre namespace).
        _ensure_external_id(
            env, "payroll_structure_%s" % suffix, "hr.payroll.structure", structure.id
        )

        # Idempotence : ne rien recréer si la règle existe déjà pour la structure.
        rule = Rule.search(
            [("code", "=", _RULE_CODE), ("struct_id", "=", structure.id)], limit=1
        )
        if rule:
            _logger.info(
                "SALARR : règle déjà présente sur '%s' (id %s), création ignorée.",
                struct_name, rule.id,
            )
        else:
            rule = Rule.create({
                "name": _RULE_NAME,
                "code": _RULE_CODE,
                "category_id": category.id,
                "struct_id": structure.id,
                "sequence": _RULE_SEQUENCE,
                "appears_on_payslip": True,
                "condition_select": "none",
                "amount_select": "code",
                "amount_python_compute": _AMOUNT_PYTHON_COMPUTE,
            })
            _logger.info(
                "SALARR : règle créée sur '%s' (id règle %s).",
                struct_name, rule.id,
            )

        # External ID de la règle SALARR (dans notre namespace).
        _ensure_external_id(
            env, "salary_rule_salarr_%s" % suffix, "hr.salary.rule", rule.id
        )
