# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import traceback

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# HEURES TRAVAILLÉES UN JOUR FÉRIÉ : majoration seule de 50 %.
#
# Décision client du 21/09/2026. La règle WORKONPUBLICHOLIDAYS paie aujourd'hui
# les heures travaillées un jour férié au taux plein :
#
#     heures x (salaire déclaré + salaire NA) / 173,33
#
# alors que ces heures sont déjà rémunérées par le salaire de base, qui couvre le
# mois entier, jours fériés compris. Ce qui reste dû au salarié, c'est la seule
# MAJORATION, de 50 % :
#
#     0,5 x heures x (salaire déclaré + salaire NA) / 173,33
#
# ---------------------------------------------------------------------------
# UNE ligne remplacée, rien d'autre
# ---------------------------------------------------------------------------
# Le corps en production est :
#
#     wages = sum(employee.contract_ids.filtered(
#         lambda c: c.state in ['open', 'open_not_declared']).mapped('wage'))
#     res = 0
#     if worked_days.get("WORKONPUBLICHOLIDAYS"):
#         total_amount = (worked_days.get("WORKONPUBLICHOLIDAYS").number_of_hours
#                         * wages / 173.33)
#         res = total_amount
#     result = res
#
# Seule la ligne « res = total_amount » change. Elle est reconnue sur son contenu
# EXACT, indentation de tête et blancs de fin mis à part : une variante
# (« res=total_amount », un commentaire ajouté, un autre coefficient) n'est PAS
# reconnue et la règle n'est pas touchée. L'indentation d'origine, les fins de
# ligne et toutes les autres lignes du corps sont conservées à l'octet près.
#
# ---------------------------------------------------------------------------
# Périmètre
# ---------------------------------------------------------------------------
# Toutes les règles de code WORKONPUBLICHOLIDAYS, quelle que soit leur structure,
# retrouvées par CODE EXACT, jamais par id. En production une seule est connue,
# sur « Paie Régulière NA » (séquence 450) ; si d'autres existent, elles portent
# la même règle métier et sont traitées de la même façon, chacune pour elle-même.
#
# NE SONT PAS TOUCHÉES : REGULWORKONPUBLICHOLIDAYS ni DAYWORKONSUNDAY. La
# recherche se fait sur l'égalité stricte du code, et une garde le revérifie règle
# par règle avant toute écriture.
#
# Aucun fichier XML du dépôt ne définit de hr.salary.rule : la mise à jour du
# module ne peut donc pas écraser cette migration. Le seul XML qui porte le code
# WORKONPUBLICHOLIDAYS (data/hr_work_entry_data.xml, noupdate="0") définit le
# TYPE D'ENTRÉE de travail du même nom, sans aucun montant.
#
# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------
#   - « PATTY_FERIE » déjà présent dans le corps      -> déjà migrée, inchangée ;
#   - ligne « res = total_amount » présente une fois  -> remplacée ;
#   - absente, ou présente plusieurs fois             -> WARNING avec le code
#     complet, RIEN n'est écrit sur cette règle, les autres restent traitées.
# Le corps produit est compilé avant écriture. Seul amount_python_compute est
# écrit : séquence, catégorie, condition et appears_on_payslip ne bougent pas.
# L'ancien et le nouveau code sont journalisés en entier, c'est la seule trace
# de récupération. Aucune exception ne remonte au build Odoo.sh.
#
# Ce script est joué AUTOMATIQUEMENT au build Odoo.sh dès que le manifeste est
# bumpé. Pour le rejouer à la main :
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "patty_ferie", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.24/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.23")
#   env.cr.commit()

_LOG = "PATTY_FERIE :"

_RULE_CODE = "WORKONPUBLICHOLIDAYS"

# La ligne remplacée, reconnue sur son contenu exact.
_OLD_LINE = "res = total_amount"

# La ligne cible. Le marqueur PATTY_FERIE qu'elle porte rend le script
# idempotent : un corps qui le contient est considéré comme déjà migré.
_MARKER = "PATTY_FERIE"
_NEW_LINE = (
    "res = total_amount * 0.5  "
    "# PATTY_FERIE : majoration seule de 50 %, décision client du 21/09/2026"
)


def _transform(current):
    """ Le corps cible, ou (None, motif) si la règle ne doit pas être écrite.

    Fonction pure, sans accès à la base : c'est elle que les tests exercent.

    Renvoie (corps, None) quand la ligne doit être remplacée, (None, None) quand
    la règle est déjà migrée, et (None, motif) quand elle n'est pas reconnue.
    """
    body = current or ""
    if _MARKER in body:
        return None, None

    # keepends : les fins de ligne d'origine sont conservées telles quelles, le
    # reste du corps est rendu à l'octet près.
    lines = body.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.strip() == _OLD_LINE]
    if len(matches) != 1:
        return None, (
            "%s ligne(s) « %s » trouvée(s) à l'identique, une seule attendue"
            % (len(matches), _OLD_LINE))

    index = matches[0]
    line = lines[index]
    content = line.rstrip("\r\n")
    ending = line[len(content):]
    indent = content[:len(content) - len(content.lstrip())]
    lines[index] = indent + _NEW_LINE + ending
    target = "".join(lines)

    try:
        compile(target, "<hr.salary.rule %s>" % _RULE_CODE, "exec")
    except SyntaxError as error:
        return None, "le corps réécrit ne compile pas (%s)" % error
    if "__" in target:
        # safe_eval refuse tout nom contenant un double souligné.
        return None, "le corps réécrit contient un double souligné"
    return target, None


def _apply(rule):
    """ Poser la majoration seule sur une règle WORKONPUBLICHOLIDAYS. """
    structure = rule.struct_id.name or "(sans structure)"

    # Garde redondante avec la recherche, par principe : aucune règle voisine
    # (REGULWORKONPUBLICHOLIDAYS, DAYWORKONSUNDAY) ne doit passer ici.
    if rule.code != _RULE_CODE:
        _logger.warning(
            "%s règle id %s de %r porte le code %r, pas %r : ignorée.",
            _LOG, rule.id, structure, rule.code, _RULE_CODE)
        return False

    current = rule.amount_python_compute or ""
    target, problem = _transform(current)

    if target is None and problem is None:
        _logger.info(
            "%s règle %s de %r (id %s) déjà migrée (marqueur %s présent), "
            "inchangée.\n--- code en base ---\n%s",
            _LOG, _RULE_CODE, structure, rule.id, _MARKER, current)
        return False

    if target is None:
        _logger.warning(
            "%s règle %s de %r (id %s) : %s. RIEN N'EST ÉCRIT sur cette règle "
            "(revue manuelle requise).\n--- code en base ---\n%s",
            _LOG, _RULE_CODE, structure, rule.id, problem, current)
        return False

    rule.write({"amount_python_compute": target})
    _logger.info(
        "%s règle %s de %r (id %s) : majoration seule de 50 %% posée.\n"
        "--- ancien amount_python_compute ---\n%s\n"
        "--- nouveau amount_python_compute ---\n%s",
        _LOG, _RULE_CODE, structure, rule.id, current, target)
    return True


def migrate(cr, version):
    try:
        env = api.Environment(cr, SUPERUSER_ID, {})
        rules = env["hr.salary.rule"].with_context(active_test=False).search([
            ("code", "=", _RULE_CODE),
        ])
        if not rules:
            _logger.warning(
                "%s aucune règle de code %r en base, RIEN N'EST ÉCRIT.",
                _LOG, _RULE_CODE)
            return

        _logger.info(
            "%s %s règle(s) %s à examiner : %s.", _LOG, len(rules), _RULE_CODE,
            ", ".join("%r (id %s, séquence %s)"
                      % (r.struct_id.name, r.id, r.sequence) for r in rules))

        written = 0
        for rule in rules:
            # Chaque règle est isolée : l'échec de l'une ne prive pas les autres.
            try:
                written += bool(_apply(rule))
            except Exception:
                _logger.warning(
                    "%s échec sur la règle id %s, les autres restent traitées.\n%s",
                    _LOG, rule.id, traceback.format_exc())

        _logger.info(
            "%s fin : %s règle(s) modifiée(s) sur %s.", _LOG, written, len(rules))
    except Exception:
        _logger.warning(
            "%s la migration a échoué, RIEN N'A ÉTÉ GARANTI.\n%s",
            _LOG, traceback.format_exc())
