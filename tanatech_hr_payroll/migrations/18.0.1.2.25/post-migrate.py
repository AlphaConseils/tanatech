# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import traceback

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# FRAIS DE TENUE DE COMPTE : plus de condition de salaire.
#
# Décision client du 23/09/2026. Les 3 000 Ar de frais bancaires s'appliquent à
# TOUS les salariés payés par virement, quel que soit leur salaire. Le seuil de
# 400 000 Ar disparaît.
#
#   avant  result = 3000 if ( employee.bank_account_id and contract.wage < 400000) else 0
#   après  result = 3000 if employee.bank_account_id else 0
#
# Seule la condition de salaire est retirée. Le montant (3 000), la condition de
# compte bancaire et la valeur par défaut (0) ne bougent pas : un salarié payé en
# espèces continue de ne rien porter.
#
# ---------------------------------------------------------------------------
# Le corps entier est remplacé, mais seulement s'il est celui attendu
# ---------------------------------------------------------------------------
# Contrairement aux migrations qui réinjectent verbatim une partie du corps, ici
# la règle tient sur une ligne et le corps cible est écrit en entier. Le
# garde-fou est donc en amont : le corps en base doit être CELUI ATTENDU, sinon
# rien n'est écrit.
#
# La comparaison ignore la mise en forme (blancs, fins de ligne, lignes vides de
# tête et de queue, et l'espace parasite après la parenthèse ouvrante que porte
# la version en production). Elle ne tolère RIEN d'autre : un montant différent,
# un autre seuil, une condition supplémentaire ou un corps sur plusieurs lignes
# ne sont pas reconnus, et la règle est laissée intacte avec un WARNING portant
# le corps complet. Les frais bancaires touchent toutes les fiches de paie :
# mieux vaut une règle non migrée et signalée qu'une règle écrasée à l'aveugle.
#
# ---------------------------------------------------------------------------
# Périmètre
# ---------------------------------------------------------------------------
# Toutes les règles de code FRAISBANC, quelle que soit leur structure,
# retrouvées par CODE EXACT, jamais par id. En production elles sont connues sur
# « Paie Régulière » et « Solde Tout Compte » (catégorie OPCOMP, séquence 5500) ;
# si d'autres existent, elles portent la même règle métier et sont traitées de la
# même façon, chacune pour elle-même.
#
# Aucun fichier XML du dépôt ne définit de hr.salary.rule : la mise à jour du
# module ne peut donc pas écraser cette migration.
#
# ATTENTION, effet de bord voulu : FRAISBANC est la ligne sortie de l'assiette
# d'arrondi par FRAIS_HORS_ARRONDI (models/hr_payslip.py, migration 1.2.23).
# Étendre les frais à tous les salariés étend donc aussi ce retrait d'assiette.
# C'est cohérent : les 3 000 Ar restent refacturés à l'identique, hors arrondi.
#
# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------
#   - « PATTY_FRAIS » déjà présent dans le corps  -> déjà migrée, inchangée ;
#   - corps identique à celui attendu             -> remplacé ;
#   - tout autre corps                            -> WARNING avec le corps
#     complet, RIEN n'est écrit sur cette règle, les autres restent traitées.
# Le corps produit est compilé avant écriture. Seul amount_python_compute est
# écrit : séquence, catégorie, condition et appears_on_payslip ne bougent pas.
# L'ancien et le nouveau corps sont journalisés en entier, c'est la seule trace
# de récupération. Aucune exception ne remonte au build Odoo.sh.
#
# Ce script est joué AUTOMATIQUEMENT au build Odoo.sh dès que le manifeste est
# bumpé. Pour le rejouer à la main :
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "patty_frais", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.25/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.24")
#   env.cr.commit()

_LOG = "PATTY_FRAIS :"

_RULE_CODE = "FRAISBANC"

# Le corps attendu en base, tel qu'il y est aujourd'hui, espace parasite après la
# parenthèse ouvrante compris.
_OLD_BODY = (
    "result = 3000 if ( employee.bank_account_id and contract.wage < 400000) "
    "else 0"
)

# Le corps cible. Le marqueur PATTY_FRAIS qu'il porte rend le script idempotent :
# un corps qui le contient est considéré comme déjà migré.
_MARKER = "PATTY_FRAIS"
_NEW_BODY = (
    "result = 3000 if employee.bank_account_id else 0  "
    "# PATTY_FRAIS : plus de seuil de salaire, décision client du 23/09/2026"
)


def _canonical(code):
    """ Forme de comparaison d'un corps de règle : sans blancs du tout.

    La mise en forme ne doit pas décider du sort d'une règle. « a and b »,
    « a  and  b » et « a and\\nb » désignent la même condition ; en revanche un
    seuil différent ou une condition supplémentaire changent bien la chaîne.
    """
    body = (code or "").replace("\r\n", "\n").replace("\r", "\n")
    return "".join(body.split())


def _transform(current):
    """ Le corps cible, ou (None, motif) si la règle ne doit pas être écrite.

    Fonction pure, sans accès à la base : c'est elle que les tests exercent.

    Renvoie (corps, None) quand le corps doit être remplacé, (None, None) quand
    la règle est déjà migrée, et (None, motif) quand le corps n'est pas celui
    attendu.
    """
    body = current or ""
    if _MARKER in body:
        return None, None

    if _canonical(body) != _canonical(_OLD_BODY):
        return None, (
            "le corps en base n'est pas celui attendu (attendu, mise en forme "
            "mise à part : %s)" % _OLD_BODY)

    target = _NEW_BODY
    try:
        compile(target, "<hr.salary.rule %s>" % _RULE_CODE, "exec")
    except SyntaxError as error:
        return None, "le corps réécrit ne compile pas (%s)" % error
    if "__" in target:
        # safe_eval refuse tout nom contenant un double souligné.
        return None, "le corps réécrit contient un double souligné"
    return target, None


def _apply(rule):
    """ Retirer le seuil de salaire d'une règle FRAISBANC. """
    structure = rule.struct_id.name or "(sans structure)"

    # Garde redondante avec la recherche, par principe.
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
            "inchangée.\n--- corps en base ---\n%s",
            _LOG, _RULE_CODE, structure, rule.id, _MARKER, current)
        return False

    if target is None:
        _logger.warning(
            "%s règle %s de %r (id %s) : %s. RIEN N'EST ÉCRIT sur cette règle "
            "(revue manuelle requise).\n--- corps en base ---\n%s",
            _LOG, _RULE_CODE, structure, rule.id, problem, current)
        return False

    rule.write({"amount_python_compute": target})
    _logger.info(
        "%s règle %s de %r (id %s) : seuil de salaire retiré, les frais "
        "s'appliquent à tout salarié payé par virement.\n"
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
