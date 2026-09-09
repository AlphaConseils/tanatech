# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# SALARR : l'arrondi au multiple de 5 000 Ar porte sur le SALAIRE NET SEUL.
#
# Défaut : l'assiette d'arrondi inclut la catégorie OPCOMP, qui porte les frais
# de tenue de compte (FRAISBANC, 3 000 Ar). L'arrondi s'applique donc à
# « net + frais » au lieu du net seul.
#
# Convention confirmée par le client (Patty, mail du 09/09/2026) : on arrondit le
# net, PUIS on ajoute les frais, sans nouvel arrondi.
#
#   net 279 060  ->  arrondi 280 000  ->  + 3 000 de frais  ->  283 000 versés
#   aujourd'hui, Odoo produit 285 000.
#
#   avant  to_pay = NET + OPCOMP + AJUST
#   après  to_pay = NET + AJUST
#
# SALNETAP (séquence 11000, catégorie NET) somme NET + OPCOMP + AJUST et n'est
# PAS touchée : les frais doivent rester dans le net à payer final, c'est
# uniquement l'assiette d'ARRONDI qui est en cause.
#
# ---------------------------------------------------------------------------
# GARDE-FOU — ce que porte réellement la catégorie OPCOMP
# ---------------------------------------------------------------------------
# Retirer OPCOMP de l'assiette retire TOUT ce que cette catégorie porte, pas
# seulement les frais bancaires. Si une autre règle y est rattachée sur une
# structure, l'intention du client n'est plus établie pour celle-là.
#
# Ce script VÉRIFIE donc, structure par structure, que la catégorie OPCOMP ne
# porte rien d'autre que FRAISBANC, et NE TOUCHE PAS une structure qui échoue —
# un WARNING nomme les règles inattendues, les autres structures restent
# traitées. Une catégorie OPCOMP vide sur une structure est normale (les
# structures NA n'ont pas nécessairement de frais bancaires) et n'empêche rien :
# la réécriture y garde les quatre corps identiques.
#
# ---------------------------------------------------------------------------
# TRANSFORMATION, pas substitution
# ---------------------------------------------------------------------------
# Le corps n'est pas remplacé par un texte figé : le script localise l'unique
# ligne « to_pay = ... » de premier niveau et n'en retire QUE le terme OPCOMP.
# Le reste — la ligne target avec son + 2500 // 5000, la ligne result, tout blanc
# ou commentaire — est conservé VERBATIM. Un corps ajusté depuis 1.1.9 n'est donc
# pas écrasé par une version d'hier.
#
# Le terme est reconnu sous ses deux positions possibles :
#   « ... + (categories.get("OPCOMP") or 0) ... »  (position courante en base)
#   « to_pay = (categories.get("OPCOMP") or 0) + ... »  (terme de tête)
#
# ---------------------------------------------------------------------------
# Périmètre et résolution
# ---------------------------------------------------------------------------
# Toutes les règles de code SALARR, quelle que soit leur structure — résolution
# par (code, struct_id), jamais par id : les ids diffèrent entre stage_2 et
# production. Quatre règles sont attendues (structures Paie Régulière SD/NA et
# Solde Tout Compte SD/NA) ; un compte différent est journalisé en WARNING sans
# rien bloquer, chaque règle étant traitée pour elle-même.
#
# ---------------------------------------------------------------------------
# Garde-fous, par règle
# ---------------------------------------------------------------------------
#   - aucun terme OPCOMP dans le corps        -> déjà migré, inchangé ;
#   - une ligne to_pay unique de premier niveau, référençant NET, portant
#     exactement un terme OPCOMP, et OPCOMP ne portant que FRAISBANC
#                                             -> réécriture ;
#   - tout autre cas                          -> WARNING avec le code complet et
#     RIEN n'est écrit sur cette règle ; les autres restent traitées.
# Le corps réécrit est compilé avant écriture. Seul amount_python_compute est
# touché : séquence, catégorie, condition et appears_on_payslip ne le sont pas.
# L'ancien code est journalisé en INFO — c'est la seule trace de récupération.
#
# Ce script est joué AUTOMATIQUEMENT au build Odoo.sh dès que le manifeste est
# bumpé (constaté sur 1.2.19 et 1.2.20 ; le boilerplate des migrations
# antérieures affirmant le contraire est erroné). La sûreté doit donc être
# acquise AVANT le merge. Pour le rejouer à la main :
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "salarr_assiette_net", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.23/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.22")
#   env.cr.commit()

_RULE_CODE = "SALARR"

# Catégorie retirée de l'assiette, et la SEULE règle qu'elle doit porter.
_REMOVED_CATEGORY = "OPCOMP"
_EXPECTED_CATEGORY_RULES = {"FRAISBANC"}

# Nombre de règles SALARR attendu (les quatre structures).
_EXPECTED_RULE_COUNT = 4

# Ligne d'assiette, de premier niveau.
_TO_PAY_RE = re.compile(r"^to_pay\s*=\s*(?P<expr>\S.*)$")

# Le terme OPCOMP, précédé de son « + » (position courante) ou suivi du sien
# (terme de tête). Un seul des deux doit s'appliquer.
_TERM = r"""\(\s*categories\s*\.\s*get\s*\(\s*["']%s["']\s*\)\s*or\s*0\s*\)""" % _REMOVED_CATEGORY
_TRAILING_TERM_RE = re.compile(r"\s*\+\s*" + _TERM)
_LEADING_TERM_RE = re.compile(_TERM + r"\s*\+\s*")
# Présence du terme, quelle que soit sa position.
_ANY_TERM_RE = re.compile(_TERM)

# L'assiette doit référencer le net : garde contre une règle d'une autre forme.
_NET_MARKER_RE = re.compile(
    r"""categories\s*\.\s*get\s*\(\s*["']NET["']\s*\)""")


def _canonical_lines(code):
    """ Lignes d'un corps de règle, fins de ligne unifiées et blancs de fin
    supprimés. L'indentation de tête est PRÉSERVÉE — elle est signifiante. """
    body = (code or "").replace("\r\n", "\n").replace("\r", "\n")
    return [line.rstrip() for line in body.strip("\n").split("\n")]


def _normalize_code(code):
    """ Forme canonique d'un corps, pour comparer sans se laisser piéger par un
    CRLF ou un blanc de fin. """
    return "\n".join(_canonical_lines(code)).strip()


def _category_rules(env, structure):
    """ Les règles de la catégorie retirée, sur cette structure. """
    return env["hr.salary.rule"].with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("category_id.code", "=", _REMOVED_CATEGORY),
    ])


def _category_is_expected(env, structure):
    """ GARDE-FOU : la catégorie retirée ne porte rien d'autre que la règle
    attendue. Une catégorie vide est acceptée. """
    rules = _category_rules(env, structure)
    codes = set(rules.mapped("code"))
    unexpected = codes - _EXPECTED_CATEGORY_RULES

    if unexpected:
        _logger.warning(
            "SALARR assiette : la catégorie %s de la structure %r porte %s "
            "règle(s) inattendue(s) : %s. Les retirer de l'assiette d'arrondi "
            "n'est pas une intention établie — RIEN N'EST ÉCRIT sur cette "
            "structure (arbitrage client requis).\n"
            "--- règles en catégorie %s ---\n%s",
            _REMOVED_CATEGORY, structure.name, len(unexpected),
            ", ".join(sorted(unexpected)), _REMOVED_CATEGORY,
            "\n".join("  %s (id %s, séquence %s) : %s"
                      % (r.code, r.id, r.sequence, r.name) for r in rules))
        return False

    _logger.info(
        "SALARR assiette : structure %r — catégorie %s conforme, elle porte %s.",
        structure.name, _REMOVED_CATEGORY,
        ", ".join("%s (id %s)" % (r.code, r.id) for r in rules) or "aucune règle")
    return True


def _strip_term(line):
    """ La ligne d'assiette privée de son terme OPCOMP, ou None si le terme n'y
    figure pas exactement une fois sous une position reconnue. """
    if len(_ANY_TERM_RE.findall(line)) != 1:
        return None

    stripped, count = _TRAILING_TERM_RE.subn("", line, count=1)
    if not count:
        stripped, count = _LEADING_TERM_RE.subn("", line, count=1)
    if not count:
        return None

    # Le terme ne devait pas être seul : il reste une assiette après retrait.
    match = _TO_PAY_RE.match(stripped)
    if not match or not match.group("expr").strip():
        return None
    return stripped


def _build(current):
    """ Le corps cible, obtenu en retirant le terme OPCOMP de l'unique ligne
    d'assiette. (None, motif) si la transformation n'est pas applicable. """
    lines = _canonical_lines(current)
    indexes = [i for i, line in enumerate(lines) if _TO_PAY_RE.match(line)]
    if len(indexes) != 1:
        return None, ("%s ligne(s) « to_pay = » de premier niveau, une seule "
                      "attendue" % len(indexes))

    index = indexes[0]
    if not _NET_MARKER_RE.search(lines[index]):
        return None, "la ligne d'assiette ne référence pas categories.get(\"NET\")"

    stripped = _strip_term(lines[index])
    if stripped is None:
        return None, ("le terme %s n'apparaît pas exactement une fois dans la "
                      "ligne d'assiette, sous une position reconnue"
                      % _REMOVED_CATEGORY)

    body = "\n".join(lines[:index] + [stripped] + lines[index + 1:])
    try:
        compile(body, "<hr.salary.rule SALARR>", "exec")
    except SyntaxError:
        return None, "le corps réécrit ne compile pas"
    return body, None


def _apply(env, rule):
    """ Retirer OPCOMP de l'assiette d'arrondi d'une règle SALARR. """
    structure = rule.struct_id
    current = rule.amount_python_compute

    if not _ANY_TERM_RE.search(current or ""):
        _logger.info(
            "SALARR assiette : règle de %r — aucun terme %s dans l'assiette, "
            "déjà migrée, inchangée.", structure.name, _REMOVED_CATEGORY)
        return

    if not _category_is_expected(env, structure):
        return

    body, problem = _build(current)
    if body is None:
        _logger.warning(
            "SALARR assiette : règle de %r — %s. RIEN N'EST ÉCRIT (revue "
            "manuelle requise).\n--- code en base ---\n%s",
            structure.name, problem, current)
        return

    if _normalize_code(current) == _normalize_code(body):
        _logger.info(
            "SALARR assiette : règle de %r déjà conforme, inchangée.",
            structure.name)
        return

    previous_body = current
    rule.write({"amount_python_compute": body})
    _logger.info(
        "SALARR assiette : règle de %r — %s retiré de l'assiette d'arrondi.\n"
        "--- ancien amount_python_compute ---\n%s\n"
        "--- nouveau amount_python_compute ---\n%s",
        structure.name, _REMOVED_CATEGORY, previous_body, body)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Résolution par code, jamais par id : chaque règle est traitée avec la
    # structure qui la porte.
    rules = env["hr.salary.rule"].with_context(active_test=False).search([
        ("code", "=", _RULE_CODE),
    ])
    if not rules:
        _logger.warning(
            "SALARR assiette : aucune règle de code %r en base — RIEN N'EST "
            "ÉCRIT.", _RULE_CODE)
        return
    if len(rules) != _EXPECTED_RULE_COUNT:
        _logger.warning(
            "SALARR assiette : %s règles %s en base, %s attendues. Chaque règle "
            "reste traitée pour elle-même, mais le périmètre mérite un coup "
            "d'oeil.", len(rules), _RULE_CODE, _EXPECTED_RULE_COUNT)

    _logger.info(
        "SALARR assiette : %s règle(s) %s à examiner : %s.",
        len(rules), _RULE_CODE,
        ", ".join("%r (id %s)" % (r.struct_id.name, r.id) for r in rules))

    for rule in rules:
        _apply(env, rule)
