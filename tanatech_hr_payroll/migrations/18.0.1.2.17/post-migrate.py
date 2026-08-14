# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Décompte du congé de maternité en jours CALENDAIRES sur la structure
# « Paie Régulière ».
#
# Même défaut que celui corrigé en 18.0.1.2.16 pour CPDED et CPALLOC : la règle
# MATOFF lit worked_days, qui renvoie des jours OUVRÉS, là où le client compte en
# jours calendaires. Constaté en production sur une salariée absente tout le mois
# de juillet 2026 : wd.number_of_days vaut 26,16 et non 30, d'où un abattement de
# 134 800 Ar au lieu des 154 600 attendus, soit la moitié de son salaire déclaré
# de 309 200 Ar.
#
#   code livré en 1.2.11              code cible (méthode 1.2.16)
#   wd = worked_days.get("MATOFF")    boucle sur hr.leave, jours calendaires,
#   if wd: ... * wd.number_of_days    plafonnés à 30
#
# Le PLAFOND à 30 est indispensable : un mois de 31 jours donnerait sinon
# -159 753 Ar, soit davantage que la moitié du salaire.
#
# La condition bascule sur la même source que le montant, comme en 18.0.1.2.16.
#
# ---------------------------------------------------------------------------
# PÉRIMÈTRE — une seule structure
# ---------------------------------------------------------------------------
# Seule « Paie Régulière » est touchée. « Paie Régulière NA » applique un
# abattement FORFAITAIRE de la moitié du salaire, rétabli en 18.0.1.2.15 et
# conforme au fichier client : elle ne compte pas de jours, il n'y a donc rien à
# y rendre calendaire. Les deux libellés normalisent vers des clés DISTINCTES,
# la structure NA ne peut pas être atteinte par erreur.
#
# ---------------------------------------------------------------------------
# La condition est DÉRIVÉE de la base, pas réécrite de mémoire
# ---------------------------------------------------------------------------
# Aucune condition MATOFF basée sur hr.leave n'existe en base : la seule
# référence lisible est la condition des règles CP de cette même structure, qui
# interroge hr.leave sur le type d'entrée LEAVE120. Ce script la lit donc en
# base et n'y substitue QUE le code de type d'entrée :
#
#   'LEAVE120'  ->  'MATOFF'
#
# Tout le reste de la chaîne — état validé, bornes de période, employé — est
# conservé verbatim. La substitution n'a lieu que si 'LEAVE120' y apparaît
# exactement une fois ; sinon la règle est sautée avec un WARNING.
#
# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------
#   - corps déjà en décompte calendaire      -> inchangé ;
#   - corps == celui livré en 18.0.1.2.11    -> réécriture ;
#   - tout autre corps                       -> WARNING avec le code complet et
#     RIEN n'est écrit.
# La condition n'est écrite que si elle diffère de la cible dérivée. Le corps
# réécrit est compilé avant écriture. Séquence, catégorie et appears_on_payslip
# ne sont pas touchés. L'ancien code est journalisé en INFO.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "matoff_calendaire", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.17/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.16")
#   env.cr.commit()

_RULE_CODE = "MATOFF"

# Structure visée, résolue par nom NORMALISÉ (casse / accents / ponctuation),
# jamais par id. « Paie Régulière » et « Paie Régulière NA » normalisent vers des
# clés distinctes : la structure NA est hors d'atteinte de ce script.
_TARGET_STRUCTURE = "Paie Régulière"

# Règles dont la condition sert de patron, sur la MÊME structure. La première
# lisible l'emporte.
_CONDITION_SOURCE_CODES = ["CPDED", "CPALLOC"]

# Codes de type d'entrée : celui du patron, celui de la cible.
_SOURCE_ENTRY_TYPE = "'LEAVE120'"
_TARGET_ENTRY_TYPE = "'MATOFF'"

# Corps livré en 18.0.1.2.11, à remplacer.
_DEFECTIVE_AMOUNT = "\n".join([
    'wd = worked_days.get("MATOFF")',
    'if wd:',
    '    result = -((contract.wage / 2 / 30) * wd.number_of_days)',
    'else:',
    '    result = 0',
])

# Corps cible : décompte calendaire plafonné à 30 jours.
_TARGET_AMOUNT = "\n".join([
    "mat_days = 0.0",
    "for l in payslip.env['hr.leave'].search([('employee_id', '=', employee.id),",
    "                                         ('state', '=', 'validate'),",
    "                                         ('holiday_status_id.work_entry_type_id.code', '=', 'MATOFF'),",
    "                                         ('request_date_from', '<=', payslip.date_to),",
    "                                         ('request_date_to', '>=', payslip.date_from)]):",
    "    # Jours calendaires, week-ends compris, conformément à la méthode client.",
    "    start = max(l.request_date_from, payslip.date_from)",
    "    stop = min(l.request_date_to, payslip.date_to)",
    "    mat_days += (stop - start).days + 1",
    "result = -((contract.wage / 2 / 30) * min(mat_days, 30))",
])

# Marqueur du décompte calendaire déjà en place.
_CALENDAR_MARKER = "mat_days += (stop - start).days + 1"
# La condition patron doit interroger hr.leave.
_LEAVE_MARKER = "payslip.env['hr.leave']"


def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation, pour apparier les libellés de structures entre environnements. """
    import unicodedata
    s = unicodedata.normalize("NFKD", label or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-zA-Z]+", " ", s).strip().lower()
    return s


def _canonical_lines(code):
    """ Lignes d'un corps de règle, fins de ligne unifiées et blancs de fin
    supprimés. L'indentation de tête est PRÉSERVÉE — elle est signifiante. """
    body = (code or "").replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip() for line in body.strip("\n").split("\n")]


def _normalize_code(code):
    """ Forme canonique d'un corps, pour comparer sans se laisser piéger par un
    CRLF ou un blanc de fin. """
    return "\n".join(_canonical_lines(code)).strip()


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
            "MATOFF calendaire : structure de paie %r introuvable, correctif "
            "sauté.", struct_name)
        return None
    if len(matches) > 1:
        _logger.warning(
            "MATOFF calendaire : %s structures de paie normalisent vers %r, "
            "correctif sauté (désambiguïsation manuelle requise).",
            len(matches), struct_name)
        return None
    return matches


def _get_rule(env, structure, rule_code):
    """ La règle (struct_id, code), ou None si absente ou multiple. """
    rules = env["hr.salary.rule"].with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("code", "=", rule_code),
    ])
    if len(rules) != 1:
        return None
    return rules


def _derive_condition(env, structure):
    """ La condition MATOFF, DÉRIVÉE de celle des règles CP de la même structure
    en n'y substituant que le code de type d'entrée. None (+ warning) si aucune
    condition patron n'est exploitable. """
    for source_code in _CONDITION_SOURCE_CODES:
        rule = _get_rule(env, structure, source_code)
        if not rule:
            continue

        condition = rule.condition_python or ""
        if _LEAVE_MARKER not in condition:
            _logger.warning(
                "MATOFF calendaire : la condition de %s n'interroge pas "
                "hr.leave, elle ne peut pas servir de patron.\n"
                "--- condition en base ---\n%s", source_code, condition)
            continue
        if condition.count(_SOURCE_ENTRY_TYPE) != 1:
            _logger.warning(
                "MATOFF calendaire : la condition de %s contient %s fois %s — "
                "substitution ambiguë, patron écarté.\n"
                "--- condition en base ---\n%s",
                source_code, condition.count(_SOURCE_ENTRY_TYPE),
                _SOURCE_ENTRY_TYPE, condition)
            continue

        derived = condition.replace(_SOURCE_ENTRY_TYPE, _TARGET_ENTRY_TYPE)
        _logger.info(
            "MATOFF calendaire : condition dérivée de celle de %s "
            "(%s -> %s).\n--- condition dérivée ---\n%s",
            source_code, _SOURCE_ENTRY_TYPE, _TARGET_ENTRY_TYPE, derived)
        return derived

    _logger.warning(
        "MATOFF calendaire : aucune condition patron exploitable parmi %s sur "
        "la structure — RIEN N'EST ÉCRIT.", ", ".join(_CONDITION_SOURCE_CODES))
    return None


def _apply(env, structure):
    """ Basculer MATOFF sur le décompte calendaire, corps et condition. """
    rule = _get_rule(env, structure, _RULE_CODE)
    if not rule:
        _logger.warning(
            "MATOFF calendaire : règle %r introuvable (ou multiple) sur la "
            "structure %r — rien à corriger.", _RULE_CODE, structure.name)
        return

    current = rule.amount_python_compute
    already_calendar = _CALENDAR_MARKER in (current or "")

    if not already_calendar and _normalize_code(current) != _normalize_code(_DEFECTIVE_AMOUNT):
        _logger.warning(
            "MATOFF calendaire : règle de %r — le corps en base ne correspond "
            "ni au décompte calendaire ni au code livré en 18.0.1.2.11. RIEN "
            "N'EST ÉCRIT (revue manuelle requise).\n--- code en base ---\n%s",
            structure.name, current)
        return

    condition = _derive_condition(env, structure)
    if condition is None:
        return

    try:
        compile(_TARGET_AMOUNT, "<hr.salary.rule MATOFF>", "exec")
    except SyntaxError:
        _logger.warning(
            "MATOFF calendaire : le corps cible ne compile pas, RIEN N'EST "
            "ÉCRIT.")
        return

    values = {}
    if _normalize_code(current) != _normalize_code(_TARGET_AMOUNT):
        values["amount_python_compute"] = _TARGET_AMOUNT
    if _normalize_code(rule.condition_python) != _normalize_code(condition):
        values["condition_python"] = condition

    if not values:
        _logger.info(
            "MATOFF calendaire : règle de %r déjà en décompte calendaire, "
            "inchangée.", structure.name)
        return

    previous_body = current
    previous_condition = rule.condition_python
    rule.write(values)
    _logger.info(
        "MATOFF calendaire : règle de %r alignée sur le décompte calendaire "
        "(champs écrits : %s).\n"
        "--- ancien amount_python_compute ---\n%s\n"
        "--- nouveau amount_python_compute ---\n%s\n"
        "--- ancienne condition_python ---\n%s\n"
        "--- nouvelle condition_python ---\n%s",
        structure.name, ", ".join(sorted(values)),
        previous_body, _TARGET_AMOUNT, previous_condition, condition)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structure = _resolve_structure(env, _TARGET_STRUCTURE)
    if not structure:
        return
    _apply(env, structure)
