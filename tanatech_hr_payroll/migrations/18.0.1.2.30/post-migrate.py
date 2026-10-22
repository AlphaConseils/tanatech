# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
import traceback

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# PRÉAVIS NON EFFECTUÉ PAR LE SALARIÉ, sur le solde de tout compte.
#
# Cas client de septembre 2026 : SONORA (solde 13,05 j, préavis de 30 j non
# effectué) a été payé de tout son solde, et l'Excel du client lui retenait le
# préavis (écart de −660 000 relevé à l'audit). Rien dans Odoo ne permettait de
# le saisir.
#
#   1. Saisie « Jours de préavis non effectués » (PREAVNE) sur le bulletin STC
#      DÉCLARÉ.
#   2. CPALLOC des deux structures STC : les jours de préavis sont d'abord pris
#      sur le solde de congés. Jours payés = max(solde - préavis, 0).
#   3. Règle RETPREAV sur les deux structures STC : ce que le solde ne couvre
#      pas est retenu, jours restants x (salaire déclaré + salaire NA) / 30.
#      La retenue s'impute d'abord sur le net à payer du STC NA, le reste sur
#      le STC déclaré (comme les avances), sans jamais rendre un net négatif.
#      Au-delà, elle est plafonnée et un message l'indique sur les bulletins.
#      Catégorie AJUST, comme les avances : elle réduit le net à payer sans
#      toucher au brut, donc ni à la CNaPS, ni à l'OSTIE, ni à l'IRSA.
#
#   RANOMENJANAHARY : solde 27,5, préavis 15  -> 12,5 j payés, rien retenu.
#   SONORA          : solde 13,05, préavis 30 -> 0 j payé,
#                     16,95 j x 659 200 / 30 = 372 448 retenus : le net NA
#                     tombe à 0, le reste est retenu sur le STC déclaré.
#
# Le double compte avec LIC02 (congés saisis à la main) et PREAV01 (préavis payé
# par l'employeur) est refusé au calcul du bulletin, dans le module
# (_tanatech_check_preavis_non_effectue).
#
# La formule de retenue reste à confirmer par le client : ses paramètres sont
# en tête du corps de RETPREAV (diviseur, base salariale) et se changent en
# base, sans migration.
#
# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------
#   - méthodes absentes du modèle            -> RIEN N'EST ÉCRIT ;
#   - structures STC : par is_stc, la déclarée est celle qui porte une
#     na_structure_id, la NA est cette na_structure_id ; autre chose -> rien ;
#   - CPALLOC : la ligne « result_qty = cp_days » (corps) et la ligne
#     « result = round(cp_days, 2) != 0 » (condition) doivent être présentes
#     une fois et une seule, sinon WARNING avec le corps complet et RIEN
#     n'est écrit sur ce champ ; « PATTY_PREAVIS » présent -> déjà migré ;
#   - RETPREAV déjà présente sans le marqueur -> WARNING, laissée telle quelle ;
#   - chaque corps produit est compilé et vérifié sans double souligné ;
#   - ancien corps journalisé en INFO avant écriture ;
#   - aucune exception ne remonte au build Odoo.sh.
#
# Pour le rejouer à la main :
#   import importlib.util
#   spec = importlib.util.spec_from_file_location(
#       "patty_preavis", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.30/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.29")
#   env.cr.commit()

_LOG = "PATTY_PREAVIS :"
_MARKER = "PATTY_PREAVIS"
_METHODS = ["_tanatech_preavis_split", "_tanatech_preavis_base", "_tanatech_preavis_disponible",
            "_tanatech_preavis_debordement"]

_INPUT_CODE = "PREAVNE"
_INPUT_NAME = "Jours de préavis non effectués"

_SLIP = "payslip.env['hr.payslip'].browse(payslip.id)"

# CPALLOC : la ligne insérée, avant la ligne d'ancrage, à la même indentation.
_CP_HOOK = (
    "# %s : les jours de préavis non effectués sont d'abord pris sur le solde\n"
    "# de congés (1.2.30). Jours payés = max(solde - préavis, 0).\n"
    "cp_days = %s._tanatech_preavis_split(cp_days)['conges_payes']\n"
) % (_MARKER, _SLIP)
_CP_ANCHORS = {
    "amount_python_compute": re.compile(r"^(?P<indent>[ \t]*)result_qty\s*=\s*cp_days\s*$", re.M),
    "condition_python": re.compile(
        r"^(?P<indent>[ \t]*)result\s*=\s*round\(\s*cp_days\s*,\s*2\s*\)\s*!=\s*0\s*$", re.M),
}

_RET_CODE = "RETPREAV"
_RET_NAME = "Retenue préavis non effectué"
_RET_SEQUENCE = 7100
# Marque des corps de la version de développement 1.2.29 (staging uniquement).
_PRERELEASE = "(1.2.29)"
_RET_CATEGORY_FROM = ["AVASP", "AVA15"]
_RET_CONDITION = (
    "# %s : des jours de préavis restent après déduction du solde de congés.\n"
    "result = %s._tanatech_preavis_split()['reste'] > 0\n"
) % (_MARKER, _SLIP)
_DISPONIBLE = (
    "# Net à payer disponible avant cette retenue (NET + accessoires + autres\n"
    "# ajustements déjà calculés), hors frais bancaires : après l'arrondi SALARR,\n"
    "# le net à payer ne doit jamais devenir négatif.\n"
    "to_pay = (categories.get(\"NET\") or 0) + (categories.get(\"OPCOMP\") or 0) "
    "+ (categories.get(\"AJUST\") or 0)\n"
    "disponible = %s._tanatech_preavis_disponible(to_pay, result_rules)\n"
) % _SLIP
# STC NA : porte la formule et ses paramètres, impute d'abord sur son net.
_RET_BODY = (
    "# %s : retenue pour préavis non effectué (1.2.30), À CONFIRMER PAR LE CLIENT.\n"
    "# ---- Paramètres -----------------------------------------------------------\n"
    "DIVISEUR = 30.0         # retenue d'un jour = salaire mensuel / DIVISEUR\n"
    "BASE_SD_PLUS_NA = True  # True : salaire déclaré + salaire NA ; False : salaire NA seul\n"
    "# ---------------------------------------------------------------------------\n"
    "# Jours saisis sur le bulletin STC déclaré (PREAVNE), moins le solde de congés\n"
    "# déjà imputé par CPALLOC : seuls les jours restants sont retenus.\n"
    "# La retenue s'impute d'abord ici, dans la limite du net disponible ; le\n"
    "# reste est imputé sur le STC déclaré (sa règle RETPREAV lit cette ligne).\n"
    "slip = %s\n"
    "jours = slip._tanatech_preavis_split()['reste']\n"
    "base = slip._tanatech_preavis_base(BASE_SD_PLUS_NA)\n"
    "totale = jours * base / DIVISEUR\n"
    "%s"
    "impute = min(totale, max(disponible, 0.0))\n"
    "# Montant = retenue TOTALE, taux = part imputée ici : total = - impute.\n"
    "# Le montant porte la retenue entière parce que l'Ariary arrondit le montant\n"
    "# stocké à la centaine : un taux journalier arrondi (22 000 au lieu de\n"
    "# 21 973,33) fausserait la part que le STC déclaré relit sur cette ligne.\n"
    "result = -totale\n"
    "result_rate = (100.0 * impute / totale) if totale else 0.0\n"
    "result_name = 'Retenue préavis non effectué (%%s j)' %% ('%%.2f' %% jours).replace('.', ',')\n"
) % (_MARKER, _SLIP, _DISPONIBLE)
# STC déclaré : le reste, dans la limite de son net. Un montant seul, sans
# taux ni base : rien ne mentionne le salaire NA sur le bulletin déclaré.
_RET_SD_CONDITION = (
    "# %s : part de la retenue de préavis que le STC NA n'a pas absorbée.\n"
    "%s"
    "result = %s._tanatech_preavis_debordement(disponible) > 0\n"
) % (_MARKER, _DISPONIBLE, _SLIP)
_RET_SD_BODY = (
    "# %s : retenue pour préavis non effectué (1.2.30), part non absorbée par le\n"
    "# STC NA. Les paramètres de la formule sont en tête de RETPREAV du STC NA.\n"
    "%s"
    "result = -%s._tanatech_preavis_debordement(disponible)\n"
) % (_MARKER, _DISPONIBLE, _SLIP)


def _check(body):
    """ Un motif de refus, ou None si le corps peut être écrit. """
    try:
        compile(body, "<hr.salary.rule>", "exec")
    except SyntaxError as error:
        return "le corps produit ne compile pas (%s)" % error
    if "__" in body:
        return "le corps produit contient un double souligné"
    return None


def _transform_cp(field, current):
    """ Le corps CPALLOC cible, ou (None, motif) s'il ne doit pas être écrit.

    Fonction pure, sans accès à la base : c'est elle que les tests exercent.
    (None, None) : déjà migré.
    """
    body = current or ""
    if _MARKER in body:
        return None, None
    matches = list(_CP_ANCHORS[field].finditer(body))
    if len(matches) != 1:
        return None, (
            "%s ligne(s) d'ancrage trouvée(s) au lieu d'une (%s)"
            % (len(matches), _CP_ANCHORS[field].pattern))
    match = matches[0]
    indent = match.group("indent")
    hook = "".join(indent + line + "\n" for line in _CP_HOOK.splitlines())
    target = body[:match.start()] + hook + body[match.start():]
    problem = _check(target)
    if problem:
        return None, problem
    return target, None


def _stc_structures(env):
    """ (structures STC déclarées, structures STC NA), par is_stc. """
    Structure = env["hr.payroll.structure"].with_context(active_test=False)
    stc = Structure.search([("is_stc", "=", True)])
    declared = stc.filtered(lambda s: s.na_structure_id)
    na = declared.mapped("na_structure_id")
    return declared, na


def _input_type(env, declared_structures):
    InputType = env["hr.payslip.input.type"].with_context(active_test=False)
    input_type = InputType.search([("code", "=", _INPUT_CODE)])
    if len(input_type) > 1:
        _logger.warning(
            "%s %s types de saisie %s en base : RIEN N'EST ÉCRIT sur les "
            "saisies (revue manuelle).", _LOG, len(input_type), _INPUT_CODE)
        return
    if not input_type:
        input_type = InputType.create({
            "name": _INPUT_NAME,
            "code": _INPUT_CODE,
            "struct_ids": [(6, 0, declared_structures.ids)],
        })
        _logger.info(
            "%s type de saisie %s créé (id %s) sur %s.", _LOG, _INPUT_CODE,
            input_type.id, ", ".join(declared_structures.mapped("name")))
        return
    missing = declared_structures - input_type.struct_ids
    if missing:
        input_type.write({"struct_ids": [(4, s.id) for s in missing]})
        _logger.info(
            "%s type de saisie %s (id %s) étendu à %s.", _LOG, _INPUT_CODE,
            input_type.id, ", ".join(missing.mapped("name")))


def _apply_cp(rule):
    values = {}
    for field in _CP_ANCHORS:
        current = rule[field] or ""
        target, problem = _transform_cp(field, current)
        if problem:
            _logger.warning(
                "%s règle %s de %r (id %s), champ %s : %s. RIEN N'EST ÉCRIT sur "
                "ce champ (revue manuelle requise).\n--- %s en base ---\n%s",
                _LOG, rule.code, rule.struct_id.name, rule.id, field, problem,
                field, current)
        elif target is not None:
            values[field] = target
    if not values:
        return False
    previous = {field: rule[field] for field in values}
    rule.write(values)
    _logger.info(
        "%s règle %s de %r (id %s) : préavis imputé sur le solde (champs : %s).\n%s",
        _LOG, rule.code, rule.struct_id.name, rule.id, ", ".join(sorted(values)),
        "\n".join("--- ancien %s ---\n%s\n--- nouveau %s ---\n%s"
                  % (f, previous[f], f, values[f]) for f in sorted(values)))
    return True


def _apply_retenue(env, structure, condition, body):
    Rule = env["hr.salary.rule"].with_context(active_test=False)
    existing = Rule.search([("struct_id", "=", structure.id), ("code", "=", _RET_CODE)])
    if existing:
        if len(existing) == 1 and _MARKER in (existing.amount_python_compute or "") \
                and _PRERELEASE in existing.amount_python_compute:
            # Corps d'une version de développement (1.2.29, staging seulement) :
            # remplacé par le corps final. Un corps marqué mais modifié depuis
            # (paramètres ajustés en base) n'est jamais réécrit.
            for code in (condition, body):
                problem = _check(code)
                if problem:
                    _logger.warning("%s %s : %s. RIEN N'EST ÉCRIT.", _LOG, _RET_CODE, problem)
                    return False
            previous = (existing.condition_python, existing.amount_python_compute)
            existing.write({"condition_python": condition, "amount_python_compute": body,
                            "name": _RET_NAME})
            _logger.info(
                "%s %s de %r (id %s) : corps de développement 1.2.29 remplacé.\n"
                "--- ancienne condition ---\n%s\n--- ancien corps ---\n%s",
                _LOG, _RET_CODE, structure.name, existing.id, previous[0], previous[1])
            return True
        if any(_MARKER in (r.amount_python_compute or "") for r in existing):
            _logger.info("%s %s déjà présente sur %r : inchangée.",
                         _LOG, _RET_CODE, structure.name)
        else:
            _logger.warning(
                "%s une règle %s existe déjà sur %r (id %s) sans le marqueur : "
                "RIEN N'EST ÉCRIT (revue manuelle).\n%s", _LOG, _RET_CODE,
                structure.name, existing.ids, existing[0].amount_python_compute)
        return False
    source = Rule.search([("struct_id", "=", structure.id),
                          ("code", "in", _RET_CATEGORY_FROM)])
    category = source.mapped("category_id")[:1]
    if not category or category.code != "AJUST":
        _logger.warning(
            "%s catégorie AJUST introuvable sur %r (règles %s) : %s NON créée.",
            _LOG, structure.name, _RET_CATEGORY_FROM, _RET_CODE)
        return False
    for code in (condition, body):
        problem = _check(code)
        if problem:
            _logger.warning("%s %s : %s. RIEN N'EST ÉCRIT.", _LOG, _RET_CODE, problem)
            return False
    rule = Rule.create({
        "name": _RET_NAME,
        "code": _RET_CODE,
        "struct_id": structure.id,
        "category_id": category.id,
        "sequence": _RET_SEQUENCE,
        "condition_select": "python",
        "condition_python": condition,
        "amount_select": "code",
        "amount_python_compute": body,
        "appears_on_payslip": True,
    })
    _logger.info("%s règle %s créée sur %r (id %s, catégorie %s, séquence %s).",
                 _LOG, _RET_CODE, structure.name, rule.id, category.code, _RET_SEQUENCE)
    return True


def migrate(cr, version):
    try:
        env = api.Environment(cr, SUPERUSER_ID, {})
        missing = [m for m in _METHODS if not callable(getattr(env["hr.payslip"], m, None))]
        if missing:
            _logger.warning(
                "%s le modèle hr.payslip n'expose pas %s : le module n'est pas à "
                "jour, RIEN N'EST ÉCRIT.", _LOG, ", ".join(missing))
            return

        declared, na = _stc_structures(env)
        if not declared or not na:
            _logger.warning(
                "%s structures STC introuvables (déclarées %s, NA %s) : RIEN "
                "N'EST ÉCRIT.", _LOG, declared.mapped("name"), na.mapped("name"))
            return
        _logger.info("%s structures STC déclarées %s, NA %s.", _LOG,
                     declared.mapped("name"), na.mapped("name"))

        _input_type(env, declared)

        rules = env["hr.salary.rule"].with_context(active_test=False).search([
            ("struct_id", "in", (declared | na).ids), ("code", "=", "CPALLOC")])
        for structure in declared | na:
            if len(rules.filtered(lambda r: r.struct_id == structure)) != 1:
                _logger.warning("%s %r ne porte pas exactement une règle CPALLOC.",
                                _LOG, structure.name)
        for rule in rules:
            try:
                _apply_cp(rule)
            except Exception:
                _logger.warning("%s échec sur CPALLOC (id %s).\n%s",
                                _LOG, rule.id, traceback.format_exc())

        retenues = [(s, _RET_CONDITION, _RET_BODY) for s in na] \
            + [(s, _RET_SD_CONDITION, _RET_SD_BODY) for s in declared]
        for structure, condition, body in retenues:
            try:
                _apply_retenue(env, structure, condition, body)
            except Exception:
                _logger.warning("%s échec de %s sur %r.\n%s", _LOG, _RET_CODE,
                                structure.name, traceback.format_exc())
    except Exception:
        _logger.warning("%s la migration a échoué, RIEN N'A ÉTÉ GARANTI.\n%s",
                        _LOG, traceback.format_exc())
