# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Proratisation de l'abattement MATOFF sur la structure de paie DÉCLARÉE.
#
# Sur le bulletin déclaré l'abattement de 50 % est légitime : la CNaPS cotise et
# versera la moitié manquante sous forme d'indemnité journalière (le non affecté,
# lui, n'ouvre droit à aucune indemnité — voir la migration 18.0.1.2.10 qui y
# neutralise l'abattement).
#
# Défaut : l'abattement est FORFAITAIRE à un demi-mois dès qu'un seul jour de
# congé maternité apparaît dans la période. Une salariée partant le 25 du mois
# subirait une retenue d'un demi-mois pour six jours de congé. Le défaut est
# invisible sur juillet 2026 — les deux salariées concernées sont absentes tout
# le mois — mais il est faux au mois de départ comme à celui de reprise.
#
# Code défectueux en base :
#
#   if worked_days.get("MATOFF"):
#       result = -( contract.wage / 2)
#   else:
#       result = 0
#
# Code cible :
#
#   wd = worked_days.get("MATOFF")
#   if wd:
#       result = -((contract.wage / 2 / 30) * wd.number_of_days)
#   else:
#       result = 0
#
# Le diviseur 30 est la convention du projet, cohérente avec BASIC
# ((contract.wage * min(jours, 30)) / 30).
#
# La garde sur None est indispensable : worked_days.get() renvoie None quand le
# type d'entrée n'est pas présent sur le bulletin. Le code défectueux testait la
# vérité de l'objet sans le déréférencer ensuite ; le code cible accède à
# wd.number_of_days et DOIT donc conserver la garde — d'où la liaison préalable
# dans `wd` plutôt qu'un double appel à get().
#
# Seul amount_python_compute est écrit. Séquence, catégorie et
# appears_on_payslip ne sont pas touchés.
#
# Prudence sur l'écriture — comparaison canonique en TROIS branches :
#   - code == code cible      -> déjà proratisé, on ne touche pas ;
#   - code == code défectueux -> on réécrit ;
#   - tout autre code         -> WARNING, on ne touche PAS. Une règle retouchée
#     à la main entre-temps ne doit pas être écrasée à l'aveugle.
# Le code remplacé est journalisé en INFO pour rester récupérable.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "matoff_sd", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.11/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.10")
#   env.cr.commit()

_RULE_CODE = "MATOFF"

# Structure visée, résolue par nom NORMALISÉ (casse / accents / ponctuation),
# jamais par id. Attention : « Paie Régulière » et « Paie Régulière NA »
# normalisent vers des clés DISTINCTES, la structure non affectée n'est donc
# jamais atteinte par ce script.
_TARGET_STRUCTURE = "Paie Régulière"

# Code défectueux attendu en base (abattement forfaitaire d'un demi-mois).
_DEFECTIVE_AMOUNT = "\n".join([
    'if worked_days.get("MATOFF"):',
    '    result = -( contract.wage / 2)',
    'else:',
    '    result = 0',
])

# Code cible : abattement proratisé au nombre de jours de congé maternité.
_TARGET_AMOUNT = "\n".join([
    'wd = worked_days.get("MATOFF")',
    'if wd:',
    '    result = -((contract.wage / 2 / 30) * wd.number_of_days)',
    'else:',
    '    result = 0',
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
            "MATOFF SD : structure de paie %r introuvable, correctif sauté.",
            struct_name)
        return None
    if len(matches) > 1:
        _logger.warning(
            "MATOFF SD : %s structures de paie normalisent vers %r, correctif "
            "sauté (désambiguïsation manuelle requise).",
            len(matches), struct_name)
        return None
    return matches


def _prorate_matoff(env, structure):
    """ Proratiser l'abattement MATOFF au nombre de jours, et uniquement là où le
    code en base est bien le code défectueux connu. """
    Rule = env["hr.salary.rule"]
    target = _normalize_code(_TARGET_AMOUNT)
    defective = _normalize_code(_DEFECTIVE_AMOUNT)

    rules = Rule.with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("code", "=", _RULE_CODE),
    ])
    if not rules:
        _logger.warning(
            "MATOFF SD : aucune règle de code %r sur la structure %r — rien à "
            "proratiser.", _RULE_CODE, structure.name)
        return

    for rule in rules:
        current = _normalize_code(rule.amount_python_compute)

        if current == target:
            _logger.info(
                "MATOFF SD : règle de %r déjà proratisée, inchangée.",
                structure.name)
            continue

        if current != defective:
            _logger.warning(
                "MATOFF SD : règle de %r — le code en base ne correspond ni au "
                "code cible ni au code défectueux attendu. RIEN N'EST ÉCRIT "
                "(revue manuelle requise).\n--- code en base ---\n%s",
                structure.name, rule.amount_python_compute)
            continue

        previous = rule.amount_python_compute
        rule.write({"amount_python_compute": _TARGET_AMOUNT})
        _logger.info(
            "MATOFF SD : abattement proratisé sur la structure %r (au lieu d'un "
            "demi-mois forfaitaire).\n"
            "--- ancien code remplacé ---\n%s\n--- nouveau code ---\n%s",
            structure.name, previous, _TARGET_AMOUNT)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structure = _resolve_structure(env, _TARGET_STRUCTURE)
    if not structure:
        return
    _prorate_matoff(env, structure)
