# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Indemnité compensatrice de congé non prise (LIC02) sur les structures de paie
# RÉGULIÈRE.
#
# Contexte : le type d'entrée LIC02 et sa règle salariale n'existent que sur les
# deux structures « Solde Tout Compte » (SD et NA). Il est donc impossible
# d'indemniser un solde de congés non pris pour un salarié toujours en poste
# (contrat ouvert, sans date_end). Les règles CPDED / CPALLOC ne se déclenchent
# que sur un hr.leave validé de type LEAVE120, donc uniquement si un congé a été
# effectivement posé — pas sur un simple solde d'allocation.
#
# Deux volets, tous deux idempotents :
#   1. rattacher le type d'entrée LIC02 EXISTANT (celui déjà porté par les
#      structures STC) à input_line_type_ids des deux structures régulières ;
#   2. y créer la règle salariale LIC02, en catégorie PRIME.
#
# Pourquoi PRIME et non INDEM (catégorie utilisée par la règle LIC02 des
# structures STC) : sur la structure « Paie Régulière », TOTAL01 (séquence 2500)
# somme BASIC + ABS + PRIME. INDEM n'y figure pas — une règle en INDEM
# s'afficherait sur le bulletin sans entrer dans le brut, donc sans effet sur le
# net ni sur les cotisations. Passer par PRIME fait entrer la ligne dans
# TOTAL01 -> GROSS -> assiette CNaPS/OSTIE/FMFP SANS toucher à TOTAL01, qui
# alimente les cotisations de 122 fiches en production. Précédent : CPALLOC
# (séquence 1210) est déjà en PRIME sur cette même structure.
#
# Séquence 1220 = juste après CPALLOC (1210), avant GROSS (3000).
#
# Aucune règle ni donnée existante n'est modifiée : les deux volets ne font
# qu'ajouter ce qui manque. Les enregistrements sont créés en ORM sans external
# ID, donc hors du périmètre de rechargement des données du module : ils
# survivent aux upgrades sans dépendre d'un noupdate. Même parti pris que la
# migration 18.0.1.1.10 (règles CPDED / CPALLOC).
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "lic02", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.5/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.4")
#   env.cr.commit()

_INPUT_TYPE_CODE = "LIC02"
_CATEGORY_CODE = "PRIME"

# Noms de référence des deux structures régulières visées. Ils sont résolus par
# nom NORMALISÉ (casse / accents / ponctuation), jamais par id : la production
# utilise des variantes de libellé différentes de stage_2 (« Paie régulière NA »
# vs « Paie Régulière NA ») et les ids divergent d'un environnement à l'autre.
_TARGET_STRUCTURES = [
    "Paie Régulière",
    "Paie Régulière NA",
]

# Corps de la règle, repris à l'identique de la règle LIC02 de la structure
# « Solde Tout Compte » (séquence 105) : l'input porte un NOMBRE DE JOURS, c'est
# la règle qui calcule le montant.
_LIC02_CONDITION = 'result = (inputs.get("LIC02") or 0)'
_LIC02_AMOUNT = "\n".join([
    'nombre_conges = (inputs.get("LIC02") or 0).amount',
    'result = (contract.wage / 24) * nombre_conges',
])

_LIC02_RULE = {
    "code": "LIC02",
    "name": "Indemnité compensatrice de congé non prise",
    "sequence": 1220,
    "category_code": _CATEGORY_CODE,
    "condition_python": _LIC02_CONDITION,
    "amount_python_compute": _LIC02_AMOUNT,
}


def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation, pour apparier les libellés de structures entre environnements. """
    import unicodedata
    import re
    s = unicodedata.normalize("NFKD", label or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-zA-Z]+", " ", s).strip().lower()
    return s


def _resolve_structures(env):
    """ { nom de référence -> hr.payroll.structure } pour les structures visées.

    Une clé normalisée peut collisionner sur plusieurs structures : dans ce cas
    on ne devine pas, on saute (désambiguïsation manuelle). """
    Structure = env["hr.payroll.structure"]

    structures_by_norm = {}
    for structure in Structure.with_context(active_test=False).search([]):
        key = _normalize(structure.name)
        structures_by_norm[key] = structures_by_norm.get(key, Structure) | structure

    resolved = {}
    for struct_name in _TARGET_STRUCTURES:
        structure = structures_by_norm.get(_normalize(struct_name))
        if not structure:
            _logger.warning(
                "LIC02 : structure de paie %r introuvable, elle est ignorée.",
                struct_name)
            continue
        if len(structure) > 1:
            _logger.warning(
                "LIC02 : %s structures de paie normalisent vers %r, elles sont "
                "ignorées (désambiguïsation manuelle requise).",
                len(structure), struct_name)
            continue
        resolved[struct_name] = structure
    return resolved


def _get_input_type(env):
    """ Le type d'entrée LIC02 EXISTANT (celui des structures STC). On n'en crée
    jamais un second : un doublon de code casserait inputs.get('LIC02'). """
    input_types = env["hr.payslip.input.type"].with_context(
        active_test=False).search([("code", "=", _INPUT_TYPE_CODE)])
    if not input_types:
        _logger.warning(
            "LIC02 : aucun type d'entrée de code %r en base — le rattachement "
            "aux structures régulières est sauté (le type doit préexister sur "
            "les structures Solde Tout Compte).", _INPUT_TYPE_CODE)
        return None
    if len(input_types) > 1:
        _logger.warning(
            "LIC02 : %s types d'entrée portent le code %r — rattachement sauté "
            "(désambiguïsation manuelle requise).",
            len(input_types), _INPUT_TYPE_CODE)
        return None
    return input_types


def _link_input_type(env, structures):
    """ VOLET 1 — ajouter le type d'entrée LIC02 à input_line_type_ids des deux
    structures régulières, sans toucher aux types déjà rattachés (Command.link,
    jamais de remplacement de la liste). """
    input_type = _get_input_type(env)
    if not input_type:
        return

    Structure = env["hr.payroll.structure"]
    # input_line_type_ids (structure) et struct_ids (type d'entrée) sont les deux
    # faces du même many2many ; on écrit sur celle qui existe réellement.
    if "input_line_type_ids" in Structure._fields:
        for struct_name, structure in structures.items():
            if input_type in structure.input_line_type_ids:
                _logger.info(
                    "LIC02 : type d'entrée déjà rattaché à %r, inchangé.",
                    struct_name)
                continue
            structure.write({
                "input_line_type_ids": [(4, input_type.id)],
            })
            _logger.info(
                "LIC02 : type d'entrée rattaché à la structure %r.", struct_name)
        return

    missing = env["hr.payroll.structure"]
    for struct_name, structure in structures.items():
        if structure in input_type.struct_ids:
            _logger.info(
                "LIC02 : type d'entrée déjà rattaché à %r, inchangé.", struct_name)
            continue
        missing |= structure
    if missing:
        input_type.write({
            "struct_ids": [(4, target.id) for target in missing],
        })
        _logger.info(
            "LIC02 : type d'entrée rattaché aux structures %s.",
            ", ".join(missing.mapped("name")))


def _get_category(env):
    """ hr.salary.rule.category de code PRIME ; None (+ warning) si absente ou
    ambiguë — on ne crée pas la règle plutôt que de la ranger au mauvais endroit. """
    categories = env["hr.salary.rule.category"].search([
        ("code", "=", _CATEGORY_CODE),
    ])
    if len(categories) != 1:
        _logger.warning(
            "LIC02 : catégorie de règle salariale de code %r introuvable ou "
            "multiple (%s trouvée(s)) — création de la règle sautée.",
            _CATEGORY_CODE, len(categories))
        return None
    return categories


def _create_salary_rules(env, structures):
    """ VOLET 2 — créer la règle LIC02 sur les deux structures régulières, là où
    elle manque uniquement. Garde d'idempotence sur (struct_id, code) : une règle
    LIC02 déjà présente n'est jamais réécrite. """
    if not structures:
        return

    Rule = env["hr.salary.rule"]
    category = None

    for struct_name, structure in structures.items():
        existing = Rule.with_context(active_test=False).search_count([
            ("struct_id", "=", structure.id),
            ("code", "=", _LIC02_RULE["code"]),
        ])
        if existing:
            _logger.info(
                "LIC02 : règle déjà présente sur %r, inchangée.", struct_name)
            continue

        if category is None:
            category = _get_category(env)
            if not category:
                return

        Rule.create({
            "name": _LIC02_RULE["name"],
            "code": _LIC02_RULE["code"],
            "sequence": _LIC02_RULE["sequence"],
            "category_id": category.id,
            "struct_id": structure.id,
            "condition_select": "python",
            "condition_python": _LIC02_RULE["condition_python"],
            "amount_select": "code",
            "amount_python_compute": _LIC02_RULE["amount_python_compute"],
            "appears_on_payslip": True,
        })
        _logger.info(
            "LIC02 : règle salariale créée sur la structure %r (séquence %s, "
            "catégorie %s).",
            struct_name, _LIC02_RULE["sequence"], _CATEGORY_CODE)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structures = _resolve_structures(env)
    _link_input_type(env, structures)
    _create_salary_rules(env, structures)
