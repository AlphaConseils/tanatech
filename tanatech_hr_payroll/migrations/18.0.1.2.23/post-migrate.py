# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
import traceback

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# PAIE D'AOÛT 2026 — quatre arbitrages client (Patty), un seul bump.
#
# A. JOURS DE CONGÉ PAYÉ (CPDED / CPALLOC, paie régulière SD et NA)
#    Défaut : jours CALENDAIRES, (fin - début).days + 1, week-ends et fériés
#    compris. Méthode client : chaque jour couvert compte 1, SAUF le dimanche
#    (0) et le jour férié (0) ; le samedi compte 1 ; une demi-journée compte 0,5.
#
#      congé du 13/08 au 26/08 + demi-journée le 31/08, Assomption le 15/08
#      (un samedi) -> 11,5 jours, là où Odoo en compte aujourd'hui 14,5.
#
#    Les structures de SOLDE DE TOUT COMPTE ne sont pas concernées : depuis
#    18.0.1.2.19 / 18.0.1.2.20 elles indemnisent le solde ACQUIS ET NON PRIS et
#    ne comptent aucun jour posé. Elles sont explicitement hors périmètre ici.
#
# B. MATERNITÉ NA (MATOFF, structures NA)
#    Défaut sur la structure NA : « s'il existe une entrée de travail MATOFF,
#    retenir la moitié du salaire », forfaitairement, quel que soit le nombre de
#    jours. La structure déclarée, elle, proratise depuis 18.0.1.2.17. Un congé
#    de 11 jours sur un salaire de 300 000 sortait donc à -150 000 en NA au lieu
#    de -55 000.
#
# C. ASSIETTE D'ARRONDI (SALARR, les quatre structures)
#    L'arrondi au multiple de 5 000 porte sur NET + OPCOMP + AJUST. OPCOMP
#    contient les frais de tenue de compte (FRAISBANC, 3 000 Ar), qui sont
#    refacturés à l'identique : ils n'ont rien à faire dans une assiette
#    d'arrondi. On les en sort, on arrondit, et SALNETAP les rajoute ensuite.
#
#      net 300 000 + frais 3 000 -> arrondi sur 300 000 -> 303 000 versés.
#
#    Ce n'est PAS la correction de la branche hotfix_salarr_assiette_net (PR 56),
#    qui retire TOUTE la catégorie OPCOMP, allocations familiales comprises. Ici
#    la liste des lignes sorties de l'assiette est une constante du module
#    (FRAIS_HORS_ARRONDI dans models/hr_payslip.py), pas une catégorie entière.
#
# D. ÉLIGIBILITÉ À LA PRIME DE MISSION (MISS, structures NA)
#    La règle MISS n'a aucune condition d'éligibilité : tout salarié ayant une
#    entrée de mission touche la prime. Un nouveau booléen de contrat
#    (tanatech_mission_eligible) la conditionne, initialisé à False sur toute la
#    société MASONTSIKA et à True ailleurs.
#
# ---------------------------------------------------------------------------
# LE CALCUL REVIENT DANS LE MODULE
# ---------------------------------------------------------------------------
# Les corps écrits ici ne portent plus la logique : ils appellent une méthode de
# tanatech_hr_payroll (models/hr_payslip.py). Le code métier redevient relisible
# en PR et couvert par des tests, et les quatre structures partagent enfin la
# même implémentation au lieu d'en recopier quatre variantes.
#
# L'appel passe par un browse explicite :
#
#   payslip.env['hr.payslip'].browse(payslip.id)._tanatech_leave_days('LEAVE120')
#
# parce que « payslip », dans le localdict des règles, est un objet ENVELOPPE du
# moteur de paie, pas un enregistrement. Ce script SONDE un localdict réel sur la
# base cible avant d'écrire (voir _probe_localdict) : si l'appel n'y est pas
# praticable, ou si « result_rules » n'y figure pas, RIEN N'EST ÉCRIT.
#
# ---------------------------------------------------------------------------
# TRANSFORMATION, pas substitution
# ---------------------------------------------------------------------------
# Comme en 18.0.1.2.16 et 18.0.1.2.19, ce qui est propre à chaque structure est
# LU en base et réinjecté VERBATIM, jamais réécrit de mémoire :
#   - la ligne result de CPDED / CPALLOC porte le diviseur (/30 ou /24) et le
#     signe ;
#   - le code de type d'entrée (LEAVE120, MATOFF) est extrait du domaine
#     réellement en base ;
#   - la ligne d'assiette de SALARR est reprise telle quelle, y compris si elle
#     a déjà été ajustée ;
#   - le taux de la maternité NA est repris de la structure déclarée, elle seule
#     fait foi.
# Seule la manière d'alimenter les jours, et l'arrondi, sont réécrits.
#
# ---------------------------------------------------------------------------
# Résolution et garde-fous
# ---------------------------------------------------------------------------
# Les structures sont résolues par nom NORMALISÉ (casse / accents /
# ponctuation), jamais par id : les ids diffèrent entre stage_2 et production.
# Une structure de paie régulière portant is_stc, ou l'inverse, est refusée.
#
# Par règle : corps déjà migré -> inchangé ; corps de la famille attendue ->
# réécriture ; tout autre corps -> WARNING avec le code complet et RIEN n'est
# écrit sur cette règle, les autres restant traitées. Chaque corps est compilé
# avant écriture. Aucune exception ne remonte : chaque volet est isolé, un échec
# de l'un n'empêche pas les autres.
#
# Ce script est joué AUTOMATIQUEMENT au build Odoo.sh dès que le manifeste est
# bumpé (constaté sur 1.2.19 et 1.2.20). Pour le rejouer à la main :
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "patty_aout", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.23/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.22")
#   env.cr.commit()

_LOG = "PATTY_AOUT :"

# ---------------------------------------------------------------------------
# Périmètre
# ---------------------------------------------------------------------------

# Noms de référence des structures, résolus par nom NORMALISÉ. Le libellé NA a
# varié (« Solde Tout Compte - NA » / « Solde Tout Compte NA ») : les deux
# normalisent vers la même clé.
_STRUCT_SD = "Paie Régulière"
_STRUCT_NA = "Paie Régulière NA"
_STRUCT_STC_SD = "Solde Tout Compte"
_STRUCT_STC_NA = "Solde Tout Compte - NA"

# Structures attendues NON STC (la résolution refuse l'inverse).
_REGULAR_STRUCTURES = [_STRUCT_SD, _STRUCT_NA]
_STC_STRUCTURES = [_STRUCT_STC_SD, _STRUCT_STC_NA]
_ALL_STRUCTURES = _REGULAR_STRUCTURES + _STC_STRUCTURES

# A : congés payés, paie régulière uniquement.
_CP_RULE_CODES = ["CPDED", "CPALLOC"]
_CP_STRUCTURES = _REGULAR_STRUCTURES

# B : maternité, structures NA, alignées sur la structure déclarée.
_MATOFF_RULE_CODE = "MATOFF"
_MATOFF_REFERENCE = _STRUCT_SD
_MATOFF_STRUCTURES = [_STRUCT_NA, _STRUCT_STC_NA]

# C : arrondi, les quatre structures.
_SALARR_RULE_CODE = "SALARR"
_SALARR_STRUCTURES = _ALL_STRUCTURES

# D : prime de mission, structures NA.
_MISS_RULE_CODE = "MISS"
_MISS_STRUCTURES = [_STRUCT_NA, _STRUCT_STC_NA]
_MISS_FIELD = "tanatech_mission_eligible"
_MISS_EXCLUDED_COMPANY = "MASONTSIKA"
# Marqueur d'initialisation : la valeur de départ du parc n'est posée QU'UNE
# FOIS. Sans lui, un rejeu écraserait les décochages manuels du client.
_MISS_INIT_PARAM = "tanatech_hr_payroll.patty_aout_mission_eligible_init"

# ---------------------------------------------------------------------------
# Corps cibles
# ---------------------------------------------------------------------------

# Le bulletin, en enregistrement réel (voir l'en-tête).
_SLIP = "payslip.env['hr.payslip'].browse(payslip.id)"

_CP_BODY = "\n".join([
    "# Jours de congé payés : dimanche et jour férié à 0, samedi à 1,",
    "# demi-journée à 0,5. Décompte porté par le module, voir",
    "# tanatech_hr_payroll/models/hr_payslip.py (_tanatech_leave_days).",
    "cp_days = %s._tanatech_leave_days(%%s)" % _SLIP,
])
_CP_CONDITION = "result = %s._tanatech_leave_days(%%s) != 0" % _SLIP

_MATOFF_BODY = "\n".join([
    "# Maternité : jours calendaires (week-ends et fériés compris), plafonnés,",
    "# indemnisés au même taux que la structure déclarée. Décompte porté par le",
    "# module, voir tanatech_hr_payroll/models/hr_payslip.py.",
    "mat_days = %s._tanatech_calendar_leave_days(%%s, %%s)" % _SLIP,
])
_MATOFF_CONDITION = (
    "result = %s._tanatech_calendar_leave_days(%%s, %%s) != 0" % _SLIP)

_SALARR_RESULT = (
    "# Les frais de tenue de compte sortent de l'assiette d'arrondi : la liste\n"
    "# est la constante FRAIS_HORS_ARRONDI de\n"
    "# tanatech_hr_payroll/models/hr_payslip.py, et le pas d'arrondi est à côté.\n"
    "result = %s._tanatech_rounding_adjustment(to_pay, result_rules)" % _SLIP)

_MISS_CONDITION = "\n".join([
    "# Prime de mission : la case « Éligible à la prime de mission » du contrat",
    "# du bulletin ET celle du contrat déclaré du même salarié doivent être",
    "# cochées. Voir tanatech_hr_payroll/models/hr_payslip.py.",
    "result = %s._tanatech_mission_eligible()" % _SLIP,
])

# ---------------------------------------------------------------------------
# Reconnaissance des corps en base
# ---------------------------------------------------------------------------

# Ligne result de premier niveau, et son expression.
_RESULT_RE = re.compile(r"^result\s*=\s*(?P<expr>\S.*)$")
# Ligne d'assiette de SALARR, de premier niveau.
_TO_PAY_RE = re.compile(r"^to_pay\s*=\s*(?P<expr>\S.*)$")
# Le terme « type de congé » du domaine, et le code qu'il porte.
_LEAVE_TYPE_RE = re.compile(
    r"""\(\s*['"]holiday_status_id\.work_entry_type_id\.code['"]\s*,\s*"""
    r"""['"]=['"]\s*,\s*['"](?P<code>[^'"]+)['"]\s*\)""")
# Le plafond de jours de la structure déclarée : min(mat_days, 30).
_CAP_RE = re.compile(
    r"min\s*\(\s*mat_days\s*,\s*(?P<cap>\d+(?:\.\d+)?)\s*\)")
# L'assiette doit référencer le net.
_NET_MARKER_RE = re.compile(r"""categories\s*\.\s*get\s*\(\s*["']NET["']\s*\)""")

# Marqueurs de familles connues.
_CALENDAR_MARKER = "cp_days += (stop - start).days + 1"
_LEAVE_MARKER = "payslip.env['hr.leave']"
_WORKED_DAYS_MARKER = "worked_days.get("
_ALLOCATION_MARKER = "payslip.env['hr.leave.allocation']"
# Marqueur d'un corps déjà migré par ce script.
_MODULE_MARKER = "_tanatech_"

# Conditions considérées comme « pas de condition » : on peut les remplacer.
_EMPTY_CONDITIONS = {"", "result = true", "result = 1", "result = 1.0"}


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation, pour apparier les libellés entre environnements. """
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


def _compiles(source, label):
    """ Le corps cible compile-t-il ? Rien n'est écrit sinon. """
    try:
        compile(source, "<hr.salary.rule %s>" % label, "exec")
    except SyntaxError:
        _logger.warning(
            "%s le code cible de %s ne compile pas — RIEN N'EST ÉCRIT.\n"
            "--- source ---\n%s", _LOG, label, source)
        return False
    return True


def _extract_result_line(code):
    """ La ligne result de premier niveau, VERBATIM, ou None s'il n'y en a pas
    exactement une. Elle porte le diviseur et le signe propres à la règle. """
    lines = [line for line in _canonical_lines(code) if _RESULT_RE.match(line)]
    if len(lines) != 1:
        return None
    return lines[0]


def _extract_entry_code(rule):
    """ Le code de type d'entrée de congé lu dans le domaine RÉELLEMENT en base
    (corps puis condition), ou None. Jamais écrit de mémoire. """
    for source in (rule.amount_python_compute, rule.condition_python):
        codes = {m.group("code") for m in _LEAVE_TYPE_RE.finditer(source or "")}
        if len(codes) == 1:
            return codes.pop()
    return None


def _get_rule(env, structure, rule_code):
    """ La règle (struct_id, code), ou un recordset vide si absente ou multiple. """
    rules = env["hr.salary.rule"].with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("code", "=", rule_code),
    ])
    if len(rules) != 1:
        if rules:
            _logger.warning(
                "%s %s règles %s sur la structure %r, une seule attendue — "
                "RIEN N'EST ÉCRIT sur cette structure.",
                _LOG, len(rules), rule_code, structure.name)
        return env["hr.salary.rule"]
    return rules


def _write_rule(rule, values, what):
    """ Écrire une règle en journalisant l'avant / après. Ne fait rien si la
    valeur est déjà celle visée (idempotence). """
    structure = rule.struct_id
    changed = {}
    for field, target in values.items():
        if _normalize_code(rule[field]) != _normalize_code(target):
            changed[field] = target
    if not changed:
        _logger.info(
            "%s %s — règle %s de %r déjà conforme, inchangée.",
            _LOG, what, rule.code, structure.name)
        return False

    previous = {field: rule[field] for field in changed}
    rule.write(changed)
    _logger.info(
        "%s %s — règle %s de %r réécrite (champs : %s).\n%s",
        _LOG, what, rule.code, structure.name, ", ".join(sorted(changed)),
        "\n".join(
            "--- ancien %s ---\n%s\n--- nouveau %s ---\n%s"
            % (field, previous[field], field, changed[field])
            for field in sorted(changed)))
    return True


# ---------------------------------------------------------------------------
# Sondage du localdict : ce que les corps cibles supposent de la base
# ---------------------------------------------------------------------------

def _probe_localdict(env):
    """ Vérifier SUR LA BASE CIBLE ce que les corps cibles supposent.

    Renvoie (methodes_ok, result_rules_ok). Le sondage construit un localdict
    réel à partir d'un bulletin existant et regarde :
      - ce qu'est vraiment la variable « payslip » (enregistrement ou
        enveloppe), journalisé pour mémoire ;
      - que payslip.env['hr.payslip'].browse(payslip.id) donne bien un
        enregistrement exposant les méthodes du module ;
      - que « result_rules » figure dans le localdict — c'est lui qui porte le
        total déjà calculé de FRAISBANC, sans lequel le volet C n'a pas de
        source.

    Sans bulletin en base (environnement vierge), on se rabat sur la présence
    des méthodes sur le modèle : le volet C est alors refusé par prudence.
    """
    Payslip = env["hr.payslip"]
    needed = [
        "_tanatech_leave_days",
        "_tanatech_calendar_leave_days",
        "_tanatech_rounding_adjustment",
        "_tanatech_mission_eligible",
    ]
    missing = [name for name in needed if not callable(getattr(Payslip, name, None))]
    if missing:
        _logger.warning(
            "%s le modèle hr.payslip n'expose pas %s — le module n'est pas à "
            "jour, RIEN N'EST ÉCRIT.", _LOG, ", ".join(missing))
        return False, False

    slip = Payslip.search([("contract_id", "!=", False)], limit=1)
    if not slip:
        _logger.warning(
            "%s aucun bulletin en base : impossible de sonder un localdict "
            "réel. Les volets A, B et D sont appliqués (ils n'utilisent que des "
            "méthodes du module, vérifiées présentes), le volet C est REFUSÉ "
            "faute d'avoir pu confirmer la présence de « result_rules ».", _LOG)
        return True, False

    try:
        localdict = slip._get_localdict()
    except Exception:
        _logger.warning(
            "%s le sondage du localdict a échoué sur le bulletin id %s — les "
            "volets A, B et D restent appliqués, le volet C est REFUSÉ.\n%s",
            _LOG, slip.id, traceback.format_exc())
        return True, False

    wrapper = localdict.get("payslip")
    _logger.info(
        "%s sondage du localdict sur le bulletin id %s : « payslip » est de "
        "type %s ; clés disponibles : %s.",
        _LOG, slip.id, type(wrapper).__name__, ", ".join(sorted(localdict)))

    result_rules_ok = "result_rules" in localdict
    if not result_rules_ok:
        _logger.warning(
            "%s « result_rules » ne figure pas dans le localdict de cette "
            "version d'Odoo : le total déjà calculé de FRAISBANC n'est pas "
            "lisible depuis la règle SALARR. Le volet C (assiette d'arrondi) "
            "est REFUSÉ, les autres restent appliqués.", _LOG)

    # L'appel exact que les corps cibles vont faire.
    try:
        probe = wrapper.env["hr.payslip"].browse(wrapper.id)
        probe._tanatech_leave_days("LEAVE120")
    except Exception:
        _logger.warning(
            "%s l'appel « payslip.env['hr.payslip'].browse(payslip.id)."
            "_tanatech_leave_days(...) » échoue sur un localdict réel — "
            "RIEN N'EST ÉCRIT.\n%s", _LOG, traceback.format_exc())
        return False, False

    _logger.info(
        "%s sondage concluant : l'appel des méthodes du module depuis une "
        "règle est praticable%s.",
        _LOG, "" if result_rules_ok else " (mais « result_rules » manque)")
    return True, result_rules_ok


# ---------------------------------------------------------------------------
# Résolution des structures
# ---------------------------------------------------------------------------

def _resolve_structures(env):
    """ { nom de référence -> hr.payroll.structure }, par nom NORMALISÉ.

    Une structure de paie régulière portant is_stc (ou l'inverse) est refusée :
    le drapeau pilote déjà le routage d'impression, une incohérence signale un
    environnement dont on ne doit rien déduire. Une clé normalisée qui
    collisionne sur plusieurs structures est ignorée, on ne devine pas.
    """
    Structure = env["hr.payroll.structure"]
    has_flag = "is_stc" in Structure._fields

    by_norm = {}
    for structure in Structure.with_context(active_test=False).search([]):
        key = _normalize(structure.name)
        by_norm[key] = by_norm.get(key, Structure) | structure

    resolved = {}
    for name in _ALL_STRUCTURES:
        found = by_norm.get(_normalize(name))
        if not found:
            _logger.warning(
                "%s structure %r introuvable en base, elle est ignorée.",
                _LOG, name)
            continue
        if len(found) > 1:
            _logger.warning(
                "%s %s structures normalisent vers %r, elles sont ignorées "
                "(désambiguïsation manuelle requise).", _LOG, len(found), name)
            continue
        expected_stc = name in _STC_STRUCTURES
        if has_flag and bool(found.is_stc) != expected_stc:
            _logger.warning(
                "%s la structure %r porte is_stc = %s alors que %s était "
                "attendu — elle est ignorée (incohérence à arbitrer).",
                _LOG, name, bool(found.is_stc), expected_stc)
            continue
        resolved[name] = found

    _logger.info(
        "%s structures résolues : %s.", _LOG,
        ", ".join("%s -> %r (id %s)" % (name, s.name, s.id)
                  for name, s in sorted(resolved.items())) or "aucune")
    return resolved


# ---------------------------------------------------------------------------
# A. Jours de congé payé (CPDED / CPALLOC, paie régulière)
# ---------------------------------------------------------------------------

def _apply_cp(env, structures):
    what = "A jours de congé"
    for name in _CP_STRUCTURES:
        structure = structures.get(name)
        if not structure:
            continue
        for rule_code in _CP_RULE_CODES:
            rule = _get_rule(env, structure, rule_code)
            if not rule:
                _logger.warning(
                    "%s %s — règle %s introuvable sur %r, rien à corriger.",
                    _LOG, what, rule_code, name)
                continue

            current = rule.amount_python_compute or ""
            if _ALLOCATION_MARKER in current:
                _logger.warning(
                    "%s %s — règle %s de %r est alimentée par le SOLDE "
                    "d'allocation (corps de solde de tout compte) alors qu'elle "
                    "est sur une structure de paie régulière. RIEN N'EST ÉCRIT "
                    "(revue manuelle requise).\n--- code en base ---\n%s",
                    _LOG, what, rule_code, name, current)
                continue

            already = _MODULE_MARKER in current
            recognised = (
                _CALENDAR_MARKER in current
                or _LEAVE_MARKER in current
                or _WORKED_DAYS_MARKER in current)
            if not already and not recognised:
                _logger.warning(
                    "%s %s — règle %s de %r : corps d'une famille inconnue. "
                    "RIEN N'EST ÉCRIT (revue manuelle requise).\n"
                    "--- code en base ---\n%s",
                    _LOG, what, rule_code, name, current)
                continue

            entry_code = _extract_entry_code(rule)
            if not entry_code:
                # Corps déjà migré : le code est dans l'appel de méthode.
                found = re.search(
                    r"_tanatech_leave_days\(\s*['\"](?P<code>[^'\"]+)['\"]",
                    current)
                entry_code = found.group("code") if found else None
            if not entry_code:
                _logger.warning(
                    "%s %s — règle %s de %r : aucun code de type d'entrée "
                    "lisible en base. RIEN N'EST ÉCRIT (le code ne doit pas "
                    "être écrit de mémoire).\n--- code en base ---\n%s",
                    _LOG, what, rule_code, name, current)
                continue

            result_line = _extract_result_line(current)
            if not result_line:
                _logger.warning(
                    "%s %s — règle %s de %r : la ligne result n'est pas unique, "
                    "impossible d'en reprendre le diviseur et le signe. RIEN "
                    "N'EST ÉCRIT.\n--- code en base ---\n%s",
                    _LOG, what, rule_code, name, current)
                continue

            body = (_CP_BODY % repr(entry_code)) + "\n" + result_line
            if not _compiles(body, "%s %s" % (rule_code, name)):
                continue

            values = {"amount_python_compute": body}

            # La condition bascule sur la MÊME source que le montant (règle de
            # maison depuis 18.0.1.2.16), mais seulement si elle appartient à
            # une famille reconnue : sans cela, un congé tombant entièrement sur
            # des dimanches produirait une ligne à zéro.
            condition = rule.condition_python or ""
            if rule.condition_select == "python" and (
                    _MODULE_MARKER in condition
                    or _LEAVE_MARKER in condition
                    or _WORKED_DAYS_MARKER in condition):
                target = _CP_CONDITION % repr(entry_code)
                if _compiles(target, "%s %s condition" % (rule_code, name)):
                    values["condition_python"] = target
            else:
                _logger.info(
                    "%s %s — règle %s de %r : condition laissée telle quelle "
                    "(condition_select = %r).",
                    _LOG, what, rule_code, name, rule.condition_select)

            _write_rule(rule, values, what)


# ---------------------------------------------------------------------------
# B. Maternité NA (MATOFF)
# ---------------------------------------------------------------------------

def _matoff_reference(env, structures):
    """ (taux unitaire, plafond, code d'entrée) lus sur la structure DÉCLARÉE.

    La structure déclarée proratise correctement depuis 18.0.1.2.17 : c'est elle
    qui fait foi, son taux n'est pas réécrit de mémoire. Sa ligne result a la
    forme « result = -((contract.wage / 2 / 30) * min(mat_days, 30)) » : on y
    remplace le min par mat_days, le plafond passant dans l'appel de méthode.
    """
    what = "B maternité NA"
    structure = structures.get(_MATOFF_REFERENCE)
    if not structure:
        _logger.warning(
            "%s %s — la structure de référence %r n'est pas résolue, impossible "
            "d'aligner les structures NA. RIEN N'EST ÉCRIT.",
            _LOG, what, _MATOFF_REFERENCE)
        return None

    rule = _get_rule(env, structure, _MATOFF_RULE_CODE)
    if not rule:
        _logger.warning(
            "%s %s — règle %s introuvable sur la structure de référence %r. "
            "RIEN N'EST ÉCRIT.", _LOG, what, _MATOFF_RULE_CODE, _MATOFF_REFERENCE)
        return None

    current = rule.amount_python_compute or ""
    result_line = _extract_result_line(current)
    if not result_line:
        _logger.warning(
            "%s %s — la ligne result de la structure de référence %r n'est pas "
            "unique. RIEN N'EST ÉCRIT.\n--- code en base ---\n%s",
            _LOG, what, _MATOFF_REFERENCE, current)
        return None

    cap = None
    found = _CAP_RE.search(result_line)
    if found:
        cap = float(found.group("cap"))
        result_line = _CAP_RE.sub("mat_days", result_line)
    elif "mat_days" in result_line:
        # Corps déjà migré : le plafond est passé dans l'appel de méthode.
        found = re.search(
            r"_tanatech_calendar_leave_days\([^,]+,\s*(?P<cap>[\d.]+)\s*\)",
            current)
        cap = float(found.group("cap")) if found else None

    if cap is None or "mat_days" not in result_line:
        _logger.warning(
            "%s %s — impossible de lire le plafond de jours et le taux sur la "
            "structure de référence %r (forme attendue « ... * min(mat_days, "
            "30) »). RIEN N'EST ÉCRIT.\n--- code en base ---\n%s",
            _LOG, what, _MATOFF_REFERENCE, current)
        return None

    entry_code = _extract_entry_code(rule)
    if not entry_code:
        found = re.search(
            r"_tanatech_calendar_leave_days\(\s*['\"](?P<code>[^'\"]+)['\"]",
            current)
        entry_code = found.group("code") if found else None
    if not entry_code:
        _logger.warning(
            "%s %s — aucun code de type d'entrée lisible sur la structure de "
            "référence %r. RIEN N'EST ÉCRIT.\n--- code en base ---\n%s",
            _LOG, what, _MATOFF_REFERENCE, current)
        return None

    # Un plafond entier s'écrit « 30 » et non « 30.0 » dans le corps produit.
    if float(cap).is_integer():
        cap = int(cap)

    _logger.info(
        "%s %s — référence lue sur %r : ligne result %r, plafond %s jours, "
        "type d'entrée %r.",
        _LOG, what, _MATOFF_REFERENCE, result_line, cap, entry_code)
    return result_line, cap, entry_code


def _apply_matoff(env, structures):
    what = "B maternité NA"
    reference = _matoff_reference(env, structures)
    if not reference:
        return
    result_line, cap, entry_code = reference

    body = (_MATOFF_BODY % (repr(entry_code), cap)) + "\n" + result_line
    condition = _MATOFF_CONDITION % (repr(entry_code), cap)
    if not _compiles(body, _MATOFF_RULE_CODE):
        return
    if not _compiles(condition, "%s condition" % _MATOFF_RULE_CODE):
        return

    for name in _MATOFF_STRUCTURES:
        structure = structures.get(name)
        if not structure:
            continue
        rule = _get_rule(env, structure, _MATOFF_RULE_CODE)
        if not rule:
            _logger.info(
                "%s %s — pas de règle %s sur %r, rien à aligner.",
                _LOG, what, _MATOFF_RULE_CODE, name)
            continue

        current = rule.amount_python_compute or ""
        recognised = (
            _MODULE_MARKER in current
            or _LEAVE_MARKER in current
            or _WORKED_DAYS_MARKER in current
            or _normalize_code(current) == "result = 0")
        if not recognised:
            _logger.warning(
                "%s %s — règle %s de %r : corps d'une famille inconnue. RIEN "
                "N'EST ÉCRIT (revue manuelle requise).\n"
                "--- code en base ---\n%s",
                _LOG, what, _MATOFF_RULE_CODE, name, current)
            continue

        values = {"amount_python_compute": body}
        if rule.condition_select == "python":
            values["condition_python"] = condition
        else:
            _logger.info(
                "%s %s — règle %s de %r : condition laissée telle quelle "
                "(condition_select = %r).",
                _LOG, what, _MATOFF_RULE_CODE, name, rule.condition_select)
        _write_rule(rule, values, what)


# ---------------------------------------------------------------------------
# C. Assiette d'arrondi (SALARR)
# ---------------------------------------------------------------------------

def _apply_salarr(env, structures, result_rules_ok):
    what = "C assiette d'arrondi"
    if not result_rules_ok:
        _logger.warning(
            "%s %s — « result_rules » n'a pas pu être confirmé dans le "
            "localdict : le total de FRAISBANC ne serait pas lisible depuis la "
            "règle. RIEN N'EST ÉCRIT sur SALARR.", _LOG, what)
        return

    for name in _SALARR_STRUCTURES:
        structure = structures.get(name)
        if not structure:
            continue
        rule = _get_rule(env, structure, _SALARR_RULE_CODE)
        if not rule:
            _logger.warning(
                "%s %s — règle %s introuvable sur %r, rien à corriger.",
                _LOG, what, _SALARR_RULE_CODE, name)
            continue

        current = rule.amount_python_compute or ""
        lines = _canonical_lines(current)
        assiette = [line for line in lines if _TO_PAY_RE.match(line)]
        if len(assiette) != 1:
            _logger.warning(
                "%s %s — règle %s de %r : %s ligne(s) « to_pay = » de premier "
                "niveau, une seule attendue. RIEN N'EST ÉCRIT (revue manuelle "
                "requise).\n--- code en base ---\n%s",
                _LOG, what, _SALARR_RULE_CODE, name, len(assiette), current)
            continue
        if not _NET_MARKER_RE.search(assiette[0]):
            _logger.warning(
                "%s %s — règle %s de %r : la ligne d'assiette ne référence pas "
                "categories.get(\"NET\"). RIEN N'EST ÉCRIT.\n"
                "--- code en base ---\n%s",
                _LOG, what, _SALARR_RULE_CODE, name, current)
            continue

        # L'assiette est reprise VERBATIM : si elle a déjà été ajustée, cet
        # ajustement est conservé. Seuls l'arrondi et le retrait des frais sont
        # réécrits.
        body = assiette[0] + "\n" + _SALARR_RESULT
        if not _compiles(body, "%s %s" % (_SALARR_RULE_CODE, name)):
            continue
        _write_rule(rule, {"amount_python_compute": body}, what)


# ---------------------------------------------------------------------------
# D. Éligibilité à la prime de mission (MISS)
# ---------------------------------------------------------------------------

def _init_mission_eligible(env):
    """ Valeur initiale du parc : False sur MASONTSIKA, True ailleurs.

    Posée UNE SEULE FOIS, sous marqueur ir.config_parameter. Un rejeu ne doit
    pas écraser les décochages manuels du client (la liste des responsables
    TANATECH à exclure est cochée à la main).
    """
    what = "D prime de mission"
    Contract = env["hr.contract"]
    if _MISS_FIELD not in Contract._fields:
        _logger.warning(
            "%s %s — le champ %s est absent de hr.contract : le module n'est "
            "pas à jour. RIEN N'EST ÉCRIT.", _LOG, what, _MISS_FIELD)
        return False

    param = env["ir.config_parameter"].sudo()
    if param.get_param(_MISS_INIT_PARAM):
        _logger.info(
            "%s %s — valeur initiale déjà posée (%s), les contrats ne sont pas "
            "retouchés : les décochages manuels du client sont préservés.",
            _LOG, what, _MISS_INIT_PARAM)
        return True

    companies = env["res.company"].search([])
    excluded = companies.filtered(
        lambda c: _normalize(c.name) == _normalize(_MISS_EXCLUDED_COMPANY))
    if not excluded:
        _logger.warning(
            "%s %s — aucune société nommée %r parmi %s : aucun contrat n'est "
            "exclu. Toutes les sociétés restent éligibles.",
            _LOG, what, _MISS_EXCLUDED_COMPANY,
            ", ".join(repr(c.name) for c in companies))

    contracts = Contract.with_context(active_test=False).search([])
    to_false = contracts.filtered(lambda c: c.company_id in excluded)
    to_true = contracts - to_false

    if to_false:
        to_false.write({_MISS_FIELD: False})
    if to_true:
        to_true.write({_MISS_FIELD: True})
    param.set_param(_MISS_INIT_PARAM, "18.0.1.2.23")

    _logger.info(
        "%s %s — valeur initiale posée : %s contrat(s) NON éligibles (sociétés "
        "%s), %s contrat(s) éligibles. Marqueur %s posé, ce volet ne sera plus "
        "rejoué.",
        _LOG, what, len(to_false),
        ", ".join(repr(c.name) for c in excluded) or "aucune",
        len(to_true), _MISS_INIT_PARAM)
    return True


def _apply_miss(env, structures):
    what = "D prime de mission"
    if not _init_mission_eligible(env):
        return

    if not _compiles(_MISS_CONDITION, "%s condition" % _MISS_RULE_CODE):
        return

    for name in _MISS_STRUCTURES:
        structure = structures.get(name)
        if not structure:
            continue
        rule = _get_rule(env, structure, _MISS_RULE_CODE)
        if not rule:
            _logger.info(
                "%s %s — pas de règle %s sur %r, rien à conditionner.",
                _LOG, what, _MISS_RULE_CODE, name)
            continue

        condition = rule.condition_python or ""
        select = rule.condition_select
        replaceable = (
            select != "python"
            or _normalize_code(condition).lower() in _EMPTY_CONDITIONS
            or _MODULE_MARKER in condition)
        if not replaceable:
            _logger.warning(
                "%s %s — règle %s de %r porte déjà une condition (%s). La "
                "remplacer perdrait un critère métier : RIEN N'EST ÉCRIT, le "
                "critère d'éligibilité doit y être ajouté à la main.\n"
                "--- condition en base ---\n%s",
                _LOG, what, _MISS_RULE_CODE, name, select, condition)
            continue
        if select == "range":
            _logger.warning(
                "%s %s — règle %s de %r est conditionnée par intervalle "
                "(condition_select = 'range') : basculer en python perdrait "
                "l'intervalle. RIEN N'EST ÉCRIT.",
                _LOG, what, _MISS_RULE_CODE, name)
            continue

        values = {"condition_python": _MISS_CONDITION}
        if select != "python":
            values["condition_select"] = "python"
            _logger.info(
                "%s %s — règle %s de %r : condition_select passe de %r à "
                "'python' (le barème, lui, n'est pas touché).",
                _LOG, what, _MISS_RULE_CODE, name, select)
        _write_rule(rule, values, what)


# ---------------------------------------------------------------------------

def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _logger.info("%s début — paie d'août 2026, volets A, B, C et D.", _LOG)

    methods_ok, result_rules_ok = _probe_localdict(env)
    if not methods_ok:
        return

    structures = _resolve_structures(env)
    if not structures:
        _logger.warning(
            "%s aucune structure résolue — RIEN N'EST ÉCRIT.", _LOG)
        return

    # Chaque volet est isolé : l'échec de l'un ne doit pas priver la base des
    # autres, et aucune exception ne doit remonter au build Odoo.sh.
    for label, handler in (
        ("A jours de congé", lambda: _apply_cp(env, structures)),
        ("B maternité NA", lambda: _apply_matoff(env, structures)),
        ("C assiette d'arrondi", lambda: _apply_salarr(env, structures, result_rules_ok)),
        ("D prime de mission", lambda: _apply_miss(env, structures)),
    ):
        try:
            handler()
        except Exception:
            _logger.warning(
                "%s le volet « %s » a échoué, les autres restent appliqués.\n%s",
                _LOG, label, traceback.format_exc())

    _logger.info("%s fin.", _LOG)
