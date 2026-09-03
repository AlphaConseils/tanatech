# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Neutralisation de l'abattement MATOFF sur la structure de paie NON AFFECTÉE.
#
# Contexte réglementaire — Code du travail malgache : le congé de maternité est
# INTÉGRALEMENT rémunéré. L'employeur en verse la moitié, la CNaPS prend l'autre
# moitié en charge sous forme d'indemnité journalière. Le principe est donc le
# maintien intégral de la rémunération : l'abattement de 50 % côté employeur
# n'est que la contrepartie d'une indemnité versée par ailleurs.
#
# Or la CNaPS calcule cette indemnité sur le salaire brut DÉCLARÉ : elle ne
# connaît que la part qui lui est déclarée. Sur l'architecture duale du projet :
#   - bulletin déclaré     : la CNaPS cotise et versera la moitié manquante,
#                            l'abattement de 50 % est correct ;
#   - bulletin non affecté : aucune cotisation, donc aucune indemnité CNaPS. Si
#                            l'employeur abat aussi 50 %, cette moitié n'est
#                            compensée par personne et la salariée perd
#                            réellement la moitié de sa rémunération non
#                            déclarée.
# L'état de paie du client applique déjà cette logique : abattement sur le
# déclaré uniquement, non affecté versé en totalité.
#
# Code défectueux en base sur la structure non affectée :
#
#   if worked_days.get("MATOFF"):
#       result = -( contract.wage / 2)
#   else:
#       result = 0
#
# Code cible : « result = 0 ».
#
# La règle n'est PAS supprimée, seulement neutralisée : la ligne reste sur le
# bulletin et la traçabilité du congé est conservée. Séquence, catégorie et
# appears_on_payslip ne sont pas touchés — seul amount_python_compute est écrit.
#
# La structure DÉCLARÉE n'est pas concernée par ce script : son abattement y est
# légitime, il est seulement mal proratisé, ce que traite la migration
# 18.0.1.2.11.
#
# Prudence sur l'écriture — comparaison canonique en TROIS branches :
#   - code == code cible      -> déjà neutralisé, on ne touche pas ;
#   - code == code défectueux -> on réécrit ;
#   - tout autre code         -> WARNING, on ne touche PAS. Une règle retouchée
#     à la main entre-temps ne doit pas être écrasée à l'aveugle.
# Le code remplacé est journalisé en INFO pour rester récupérable.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "matoff_na", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.10/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.9")
#   env.cr.commit()

_RULE_CODE = "MATOFF"

# Structure visée, résolue par nom NORMALISÉ (casse / accents / ponctuation),
# jamais par id : la production utilise des variantes de libellé et les ids
# divergent entre environnements.
_TARGET_STRUCTURE = "Paie Régulière NA"

# Code défectueux attendu en base (abattement forfaitaire d'un demi-mois).
_DEFECTIVE_AMOUNT = "\n".join([
    'if worked_days.get("MATOFF"):',
    '    result = -( contract.wage / 2)',
    'else:',
    '    result = 0',
])

# Code cible : aucun abattement sur le non affecté.
_TARGET_AMOUNT = "result = 0"


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
    """ Forme canonique d'un corps de règle : fins de ligne unifiées, blancs de
    fin supprimés, lignes vides de tête/queue ignorées. L'indentation de tête est
    PRÉSERVÉE — elle est signifiante en Python. """
    lines = (code or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def _resolve_structure(env, struct_name):
    """ La structure de paie désignée, ou None (+ warning) si absente ou si
    plusieurs structures normalisent vers le même libellé. """
    Structure = env["hr.payroll.structure"]

    matches = Structure
    for structure in Structure.with_context(active_test=False).search([]):
        if _normalize(structure.name) == _normalize(struct_name):
            matches |= structure

    if not matches:
        _logger.warning(
            "MATOFF NA : structure de paie %r introuvable, correctif sauté.",
            struct_name)
        return None
    if len(matches) > 1:
        _logger.warning(
            "MATOFF NA : %s structures de paie normalisent vers %r, correctif "
            "sauté (désambiguïsation manuelle requise).",
            len(matches), struct_name)
        return None
    return matches


def _neutralize_matoff(env, structure):
    """ Ramener l'abattement MATOFF à zéro, et uniquement là où le code en base
    est bien le code défectueux connu. """
    Rule = env["hr.salary.rule"]
    target = _normalize_code(_TARGET_AMOUNT)
    defective = _normalize_code(_DEFECTIVE_AMOUNT)

    rules = Rule.with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("code", "=", _RULE_CODE),
    ])
    if not rules:
        _logger.warning(
            "MATOFF NA : aucune règle de code %r sur la structure %r — rien à "
            "neutraliser.", _RULE_CODE, structure.name)
        return

    for rule in rules:
        current = _normalize_code(rule.amount_python_compute)

        if current == target:
            _logger.info(
                "MATOFF NA : règle de %r déjà neutralisée, inchangée.",
                structure.name)
            continue

        if current != defective:
            _logger.warning(
                "MATOFF NA : règle de %r — le code en base ne correspond ni au "
                "code cible ni au code défectueux attendu. RIEN N'EST ÉCRIT "
                "(revue manuelle requise).\n--- code en base ---\n%s",
                structure.name, rule.amount_python_compute)
            continue

        previous = rule.amount_python_compute
        rule.write({"amount_python_compute": _TARGET_AMOUNT})
        _logger.info(
            "MATOFF NA : abattement neutralisé sur la structure %r (le non "
            "affecté n'ouvre droit à aucune indemnité CNaPS).\n"
            "--- ancien code remplacé ---\n%s\n--- nouveau code ---\n%s",
            structure.name, previous, _TARGET_AMOUNT)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structure = _resolve_structure(env, _TARGET_STRUCTURE)
    if not structure:
        return
    _neutralize_matoff(env, structure)
