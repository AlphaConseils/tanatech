# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Neutralisation de CPDED sur les structures SOLDE TOUT COMPTE.
#
# CPDED et CPALLOC forment une SUBSTITUTION en paie régulière : le jour de congé
# posé est déjà payé dans BASIC au taux ordinaire, CPDED le retire (/30) et
# CPALLOC le repaie au taux congé (/24). Le solde net pour le salarié est
# +wage/120 par jour, c'est-à-dire l'écart entre les deux taux. Aucune des deux
# règles n'a de sens seule.
#
# La migration 18.0.1.2.19 a basculé CPALLOC des structures STC sur le SOLDE
# RESTANT. CPALLOC n'y est donc plus la contrepartie de CPDED : les jours posés
# dans le mois du départ sont sortis du solde par leaves_taken et ne sont plus
# repayés nulle part. CPDED laissé en l'état retire wage/30 par jour de congé
# posé en août SANS contrepartie — le salarié perdrait la rémunération de jours
# de congé qu'il a régulièrement pris.
#
# À noter : BASIC des structures STC est proratisé sur les jours CALENDAIRES de
# présence entre le début de période et contract.date_end (motif posé par
# 18.0.1.2.12 puis 18.0.1.2.14), et non sur les jours travaillés. Il n'y a donc
# pas de double déduction aujourd'hui : le défaut est la perte de contrepartie,
# pas un doublon.
#
#   code en base (famille « jours pris »)     code cible
#   boucle sur hr.leave ou worked_days        result = 0
#   result = -(contract.wage / 30.0) * cp_days
#
# La règle n'est PAS supprimée, seulement neutralisée : la ligne reste sur la
# structure et l'historique des bulletins déjà calculés est conservé. Même parti
# pris que 18.0.1.2.10 pour MATOFF. Le rapport de solde de tout compte filtre les
# lignes à total non nul, la ligne neutralisée n'apparaît donc pas à l'impression.
#
# condition_python n'est pas touchée : elle ne fait que décider de l'affichage
# d'une ligne désormais nulle.
#
# PÉRIMÈTRE — les deux structures STC, et elles seules, sélectionnées sur is_stc
# comme en 18.0.1.2.19. Les structures de paie RÉGULIÈRE gardent leur couple
# CPDED / CPALLOC intact : il y est correct.
#
# Garde-fous — comparaison canonique en trois branches :
#   - corps == « result = 0 »                 -> déjà neutralisé, on ne touche pas ;
#   - corps de la famille « jours pris » avec une ligne result unique portant
#     cp_days                                 -> réécriture ;
#   - tout autre corps                        -> WARNING avec le code complet et
#     RIEN n'est écrit.
# L'ancien code est journalisé en INFO — c'est la seule trace de récupération.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "cpded_neutralise_stc", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.20/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.19")
#   env.cr.commit()

_RULE_CODE = "CPDED"

_TARGET_AMOUNT = "result = 0"

# Filet de sécurité si aucune structure ne porte is_stc. Résolution par nom
# NORMALISÉ, jamais par id.
_FALLBACK_STRUCTURE_NAMES = [
    "Solde Tout Compte",
    "Solde Tout Compte - NA",
]

# Ligne result de premier niveau.
_RESULT_RE = re.compile(r"^result\s*=\s*\S.*$")

# Marqueurs de la famille « jours pris », les deux reconnues depuis 18.0.1.2.16.
_LEAVE_MARKER = "payslip.env['hr.leave'].search("
_WORKED_DAYS_MARKER = "worked_days.get('LEAVE120')"


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


def _extract_result_line(code):
    """ La ligne result de premier niveau, ou None s'il n'y en a pas exactement
    une. Sert ici à s'assurer qu'on neutralise bien une déduction calculée sur
    cp_days, et non un corps inconnu. """
    lines = [line for line in _canonical_lines(code) if _RESULT_RE.match(line)]
    if len(lines) != 1:
        return None
    return lines[0]


def _is_days_taken(code):
    body = code or ""
    return _LEAVE_MARKER in body or _WORKED_DAYS_MARKER in body


def _resolve_structures(env):
    """ Les structures de solde de tout compte, par is_stc, avec repli par nom
    normalisé. Une structure qui ne porte pas is_stc est refusée par le repli. """
    Structure = env["hr.payroll.structure"]
    all_structures = Structure.with_context(active_test=False).search([])

    has_flag = "is_stc" in Structure._fields
    if has_flag:
        structures = all_structures.filtered(lambda s: s.is_stc)
        if structures:
            _logger.info(
                "CPDED STC : %s structure(s) retenue(s) sur is_stc : %s.",
                len(structures), ", ".join(repr(s.name) for s in structures))
            return structures
        _logger.warning(
            "CPDED STC : aucune structure ne porte is_stc — repli sur la "
            "résolution par nom.")
    else:
        _logger.warning(
            "CPDED STC : le champ is_stc est absent de hr.payroll.structure — "
            "repli sur la résolution par nom.")

    by_norm = {}
    for structure in all_structures:
        key = _normalize(structure.name)
        by_norm[key] = by_norm.get(key, Structure) | structure

    structures = Structure
    for struct_name in _FALLBACK_STRUCTURE_NAMES:
        found = by_norm.get(_normalize(struct_name))
        if not found:
            _logger.warning(
                "CPDED STC : structure %r introuvable, elle est ignorée.",
                struct_name)
            continue
        if len(found) > 1:
            _logger.warning(
                "CPDED STC : %s structures normalisent vers %r, elles sont "
                "ignorées (désambiguïsation manuelle requise).",
                len(found), struct_name)
            continue
        if has_flag and not found.is_stc:
            _logger.warning(
                "CPDED STC : la structure %r ne porte pas is_stc, elle est "
                "ignorée — le repli par nom ne doit pas atteindre une structure "
                "de paie régulière.", struct_name)
            continue
        structures |= found

    if structures:
        _logger.info(
            "CPDED STC : %s structure(s) retenue(s) par nom : %s.",
            len(structures), ", ".join(repr(s.name) for s in structures))
    return structures


def _get_rule(env, structure, rule_code):
    """ La règle (struct_id, code), ou None si absente ou multiple. """
    rules = env["hr.salary.rule"].with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("code", "=", rule_code),
    ])
    if len(rules) != 1:
        return None
    return rules


def _apply(env, structure):
    """ Neutraliser CPDED sur une structure STC. """
    rule = _get_rule(env, structure, _RULE_CODE)
    if not rule:
        _logger.warning(
            "CPDED STC : règle %s introuvable (ou multiple) sur la structure "
            "%r — rien à corriger.", _RULE_CODE, structure.name)
        return

    current = rule.amount_python_compute

    if _normalize_code(current) == _normalize_code(_TARGET_AMOUNT):
        _logger.info(
            "CPDED STC : règle %s de %r déjà neutralisée, inchangée.",
            _RULE_CODE, structure.name)
        return

    result_line = _extract_result_line(current)
    if not _is_days_taken(current) or not result_line or "cp_days" not in result_line:
        _logger.warning(
            "CPDED STC : règle %s de %r — le corps n'est pas une déduction de "
            "jours pris reconnue (famille hr.leave / worked_days avec une ligne "
            "result unique sur cp_days). RIEN N'EST ÉCRIT (revue manuelle "
            "requise).\n--- code en base ---\n%s",
            _RULE_CODE, structure.name, current)
        return

    previous_body = current
    rule.write({"amount_python_compute": _TARGET_AMOUNT})
    _logger.info(
        "CPDED STC : règle %s de %r neutralisée.\n"
        "--- ancien amount_python_compute ---\n%s\n"
        "--- nouveau amount_python_compute ---\n%s",
        _RULE_CODE, structure.name, previous_body, _TARGET_AMOUNT)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structures = _resolve_structures(env)
    if not structures:
        _logger.warning(
            "CPDED STC : aucune structure de solde de tout compte résolue — "
            "RIEN N'EST ÉCRIT.")
        return
    for structure in structures:
        _apply(env, structure)
