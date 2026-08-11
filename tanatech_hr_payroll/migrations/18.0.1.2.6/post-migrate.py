# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Correctif du calcul de la règle LIC02 sur les structures SOLDE TOUT COMPTE
# (« Solde Tout Compte » et « Solde Tout Compte - NA »).
#
# Code défectueux en base :
#
#   wages = sum(employee.contract_ids.filtered(
#       lambda c: c.state in ['open', 'open_not_declared']).mapped('wage'))
#   res = 0
#   nombre_conges = (inputs.get("LIC02") or 0).amount
#   result = (wages / 24) * nombre_conges
#
# Deux défauts :
#   1. sur un solde de tout compte les contrats sont CLOS (state = 'close'), donc
#      le filtre ne retient rien, wages vaut 0 et l'indemnité est toujours nulle.
#      Constaté en production : 7 jours dus, ligne LIC02 calculée à 0 ;
#   2. la somme SD + NA est calculée sur CHAQUE bulletin séparément — si les
#      contrats étaient ouverts, l'indemnité serait versée deux fois.
#
# Correctif : même formule que les règles LIC02 des structures régulières créées
# par la migration 18.0.1.2.5 — l'assiette est le salaire du contrat DU bulletin
# (contract.wage), ce qui règle les deux défauts d'un coup : plus de dépendance à
# l'état du contrat, et chaque bulletin n'indemnise que son propre contrat.
#
# Seul amount_python_compute est touché. La catégorie (INDEM), la séquence, la
# condition et tous les autres champs restent inchangés : sur les structures STC
# la ligne entre déjà dans le brut via INDEM, il n'y a rien à y corriger.
#
# Idempotence : la réécriture n'a lieu que si le code en base diffère du code
# cible (comparaison à blancs de fin normalisés). Un second passage ne réécrit
# rien. Le code remplacé est journalisé en INFO pour rester récupérable.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "lic02_stc", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.6/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.5")
#   env.cr.commit()

_RULE_CODE = "LIC02"

# Structures visées, résolues par nom NORMALISÉ (casse / accents / ponctuation),
# jamais par id : les ids divergent entre environnements et le libellé NA a varié
# (« Solde Tout Compte - NA » vs « Solde Tout Compte NA »), les deux se
# normalisant vers la même clé. Les structures RÉGULIÈRES ne sont pas concernées :
# la migration 18.0.1.2.5 y a déjà créé la règle avec la bonne formule.
_TARGET_STRUCTURES = [
    "Solde Tout Compte",
    "Solde Tout Compte - NA",
]

# Formule cible, strictement identique à celle des règles LIC02 des structures
# régulières (18.0.1.2.5). L'input porte un NOMBRE DE JOURS.
_TARGET_AMOUNT = "\n".join([
    'nombre_conges = (inputs.get("LIC02") or 0).amount',
    'result = (contract.wage / 24) * nombre_conges',
])


def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation, pour apparier les libellés de structures entre environnements. """
    import unicodedata
    import re
    s = unicodedata.normalize("NFKD", label or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-zA-Z]+", " ", s).strip().lower()
    return s


def _normalize_code(code):
    """ Forme canonique d'un corps de règle pour la comparaison : fins de ligne
    unifiées, blancs de fin supprimés, lignes vides de tête/queue ignorées.

    Évite de réécrire une règle déjà correcte qui ne différerait que par un
    '\\r\\n' ou une espace en fin de ligne — sinon la migration ne serait pas
    idempotente d'un environnement à l'autre. """
    lines = (code or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


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
                "LIC02 STC : structure de paie %r introuvable, elle est ignorée.",
                struct_name)
            continue
        if len(structure) > 1:
            _logger.warning(
                "LIC02 STC : %s structures de paie normalisent vers %r, elles "
                "sont ignorées (désambiguïsation manuelle requise).",
                len(structure), struct_name)
            continue
        resolved[struct_name] = structure
    return resolved


def _fix_amount_compute(env, structures):
    """ Réaligner amount_python_compute des règles LIC02 des structures STC sur
    la formule cible, uniquement là où le code en base en diffère. """
    Rule = env["hr.salary.rule"]
    target = _normalize_code(_TARGET_AMOUNT)

    for struct_name, structure in structures.items():
        # Résolution par (struct_id, code), jamais par id de règle.
        rules = Rule.with_context(active_test=False).search([
            ("struct_id", "=", structure.id),
            ("code", "=", _RULE_CODE),
        ])
        if not rules:
            _logger.warning(
                "LIC02 STC : aucune règle de code %r sur la structure %r — "
                "rien à corriger.", _RULE_CODE, struct_name)
            continue

        for rule in rules:
            if _normalize_code(rule.amount_python_compute) == target:
                _logger.info(
                    "LIC02 STC : règle de la structure %r déjà sur la formule "
                    "cible, inchangée.", struct_name)
                continue

            previous = rule.amount_python_compute
            rule.write({"amount_python_compute": _TARGET_AMOUNT})
            _logger.info(
                "LIC02 STC : amount_python_compute corrigé sur la structure %r.\n"
                "--- ancien code remplacé ---\n%s\n--- nouveau code ---\n%s",
                struct_name, previous, _TARGET_AMOUNT)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structures = _resolve_structures(env)
    _fix_amount_compute(env, structures)
