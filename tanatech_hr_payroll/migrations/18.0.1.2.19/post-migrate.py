# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# CPALLOC des structures SOLDE TOUT COMPTE : indemniser le solde de congés
# ACQUIS ET NON PRIS, et non les congés PRIS pendant la période.
#
# Défaut : les règles CPALLOC des deux structures STC sont des copies conformes
# de celles de la paie régulière (migration 18.0.1.2.9). Elles comptent les jours
# de congé POSÉS sur le mois. C'est correct en paie régulière — CPDED y retire le
# jour de congé au taux ordinaire (/30) et CPALLOC le repaie au taux congé (/24),
# les deux règles forment une SUBSTITUTION — mais c'est faux sur un solde de tout
# compte : au départ d'un salarié, ce qui doit être payé est le solde RESTANT.
#
# Constaté sur la paie d'août 2026 : sept départs, environ 4 000 000 Ar d'écart.
# RAKOTO SEDSON MIALY ressort à 1 110 000 Ar sur son bulletin NA au lieu des
# -290 000 attendus, RAHARIVELO à 400 000 au lieu de 865 000.
#
# Règle confirmée par le client (Patty, mail du 09/09/2026), vérifiée au centime
# sur les sept départs TANATECH du fichier client :
#
#   indemnité = (salaire de base du contrat / 24) x jours de solde restant
#
# Le diviseur 24 ne change pas — et il n'est PAS réécrit ici : il est extrait de
# la ligne result en base et réinjecté VERBATIM (voir plus bas). Seule la SOURCE
# des jours change.
#
#   avant (jours PRIS sur la période)        après (solde RESTANT au départ)
#   boucle sur hr.leave, jours calendaires   boucle sur hr.leave.allocation,
#   du congé chevauchant la période          number_of_days - leaves_taken
#
# ---------------------------------------------------------------------------
# Les jours passent en QUANTITÉ, pas seulement dans le montant
# ---------------------------------------------------------------------------
# Le rapport de solde de tout compte imprime line.quantity. Une règle en
# amount_select = 'code' qui ne pose pas result_qty sort à 1 : le bulletin
# afficherait « 1 | 865 000 » sans jamais nommer les 28 jours indemnisés — une
# ligne inopposable au salarié. Le corps cible sépare donc les deux :
#
#   result_qty = cp_days              -> les jours, colonne Quantité
#   result = (contract.wage / 24.0)   -> le taux journalier, colonne Montant
#
# hr.payslip.line.total vaut montant x quantité x taux / 100, et c'est ce TOTAL
# que la catégorie agrège : le brut et le net sont donc rigoureusement inchangés
# par rapport à une règle qui porterait tout dans le montant. Seul l'affichage
# gagne l'information.
#
# ---------------------------------------------------------------------------
# PÉRIMÈTRE — les deux structures STC, et elles seules
# ---------------------------------------------------------------------------
# Les structures sont sélectionnées sur le drapeau is_stc (tanatech_hr_contract),
# qui pilote déjà le routage d'impression vers le rapport de solde de tout compte
# et couvre les deux étages, SD et NA. Les structures de paie RÉGULIÈRE ne sont
# pas concernées : leur couple CPDED / CPALLOC est correct et n'est pas touché.
#
# Filet de sécurité : si aucune structure ne porte is_stc (drapeau non renseigné
# sur un environnement), on retombe sur la résolution par nom NORMALISÉ (casse /
# accents / ponctuation), jamais par id — les ids et les libellés divergent entre
# stage_2 et production. Les structures retenues sont journalisées dans les deux
# cas, et une structure NON STC atteinte par le filet est refusée.
#
# ---------------------------------------------------------------------------
# Ce que le script LIT plutôt que de le reconstruire
# ---------------------------------------------------------------------------
#   - la LIGNE RESULT est extraite du corps propre à chaque structure et reprise
#     verbatim. Elle porte le diviseur (/24.0) et le signe : ce script ne les
#     réécrit pas, il ne change QUE la manière d'alimenter cp_days ;
#   - le TERME DE TYPE DE CONGÉ (LEAVE120) est extrait du domaine réellement en
#     base, sur la règle elle-même puis, à défaut, sur les règles CP voisines.
#     Le code de type d'entrée n'est jamais écrit de mémoire.
#
# ---------------------------------------------------------------------------
# Le solde restant
# ---------------------------------------------------------------------------
#   somme, sur les hr.leave.allocation de l'employé en état 'validate' dont le
#   type de congé porte le type d'entrée LEAVE120, de
#   (number_of_days - leaves_taken).
#
# leaves_taken décompte TOUS les congés validés imputés sur l'allocation, y
# compris ceux posés dans le mois du départ : les jours pris en août sont donc
# déjà sortis du solde et ne peuvent pas être payés deux fois.
#
# Le solde n'est PAS plancheé à zéro. Un salarié ayant consommé plus que son
# acquis produit une ligne NÉGATIVE, c'est-à-dire la récupération du congé pris
# d'avance — arithmétiquement correct, et préférable à un plancher qui masquerait
# une anomalie de données. La condition ne déclenche la règle que si le solde est
# non nul, un solde à zéro n'affiche donc aucune ligne.
#
# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------
# Le modèle hr.leave.allocation et les champs lus (employee_id, state,
# holiday_status_id, number_of_days, leaves_taken) sont VÉRIFIÉS présents avant
# toute écriture : sur une version où l'un d'eux manquerait, le script s'arrête
# sans rien écrire plutôt que de poser une règle qui planterait au calcul.
#
# Par règle et par structure, comparaison canonique en trois branches :
#   - corps déjà sur le solde d'allocation   -> inchangé ;
#   - corps de la famille « jours pris » (hr.leave ou worked_days) ET ligne
#     result unique extraite ET terme de type de congé disponible -> réécriture ;
#   - tout autre corps                       -> WARNING avec le code complet et
#     RIEN n'est écrit sur cette règle ; les autres restent traitées.
#
# La condition bascule sur la MÊME source que le montant, comme en 18.0.1.2.16 et
# 18.0.1.2.17 : sinon la règle ne se déclencherait que pour les salariés ayant
# posé un congé dans le mois du départ, c'est-à-dire presque personne.
#
# Corps et condition cibles sont compilés avant écriture. Seuls
# amount_python_compute et condition_python sont écrits. Séquence, catégorie et
# appears_on_payslip ne sont pas touchés. L'ancien code est journalisé en INFO —
# c'est la seule trace de récupération.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "cpalloc_solde_stc", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.19/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.18")
#   env.cr.commit()

_RULE_CODE = "CPALLOC"

# Règles dont le domaine peut servir à retrouver le terme de type de congé, par
# ordre de préférence, sur la structure courante puis sur les autres STC.
_DOMAIN_SOURCE_CODES = ["CPALLOC", "CPDED"]

# Filet de sécurité si aucune structure ne porte is_stc. Résolution par nom
# NORMALISÉ, jamais par id. Le libellé NA a varié (« Solde Tout Compte - NA » vs
# « Solde Tout Compte NA ») : les deux normalisent vers la même clé.
_FALLBACK_STRUCTURE_NAMES = [
    "Solde Tout Compte",
    "Solde Tout Compte - NA",
]

# Modèle et champs indispensables au corps cible.
_ALLOCATION_MODEL = "hr.leave.allocation"
_ALLOCATION_FIELDS = [
    "employee_id",
    "state",
    "holiday_status_id",
    "number_of_days",
    "leaves_taken",
]

# Corps cible. __DOMAIN__ reçoit le domaine des allocations, __UNIT__ le montant
# UNITAIRE extrait de la ligne result en base — le diviseur n'est jamais écrit
# ici. Les marqueurs sont textuels et non des « %s » : une expression contenant
# un « % » ne doit pas casser la construction.
_BALANCE_BODY = "\n".join([
    "# Solde de congés ACQUIS ET NON PRIS à la date de sortie : sur un solde de",
    "# tout compte, c'est ce reliquat qui est indemnisé, pas les jours posés",
    "# dans le mois. leaves_taken couvre déjà les congés du mois du départ.",
    "cp_days = 0.0",
    "for a in payslip.env['hr.leave.allocation'].search(__DOMAIN__):",
    "    cp_days += a.number_of_days - a.leaves_taken",
    "# Les JOURS sont portés par la quantité, le taux journalier par le montant :",
    "# le bulletin imprime « 28,00 » au lieu de « 1 ». total = montant x quantité",
    "# x taux / 100, le brut agrégé par la catégorie est donc inchangé.",
    "result_qty = cp_days",
    "result = __UNIT__",
])

# Condition cible : même source que le montant. Une ligne n'apparaît que si le
# solde est non nul ; un solde négatif (congé pris d'avance) est conservé.
_BALANCE_CONDITION = "\n".join([
    "cp_days = 0.0",
    "for a in payslip.env['hr.leave.allocation'].search(__DOMAIN__):",
    "    cp_days += a.number_of_days - a.leaves_taken",
    "result = round(cp_days, 2) != 0",
])

# Domaine des allocations. Le terme de type de congé est injecté tel qu'il est
# lu en base ; l'employé et l'état sont communs à hr.leave et à
# hr.leave.allocation, ils sont donc écrits directement.
_ALLOCATION_DOMAIN = (
    "[('employee_id', '=', employee.id), "
    "('state', '=', 'validate'), "
    "__TERM__]"
)

# Terme de type de congé, dans le domaine réellement en base.
_LEAVE_TYPE_RE = re.compile(
    r"""\(\s*['"]holiday_status_id\.work_entry_type_id\.code['"]\s*,\s*"""
    r"""['"]=['"]\s*,\s*['"][^'"]+['"]\s*\)""")

# Ligne result de premier niveau, et son expression.
_RESULT_RE = re.compile(r"^result\s*=\s*(?P<expr>\S.*)$")
# Ligne de quantité déjà posée par un passage précédent.
_RESULT_QTY_RE = re.compile(r"^result_qty\s*=\s*cp_days\s*$")
# « result = <unité> * cp_days » et le produit écrit dans l'autre sens.
_UNIT_SUFFIX_RE = re.compile(r"^(?P<unit>.+?)\s*\*\s*cp_days$")
_UNIT_PREFIX_RE = re.compile(r"^cp_days\s*\*\s*(?P<unit>.+?)$")

# Marqueur du solde d'allocation déjà en place.
_BALANCE_MARKER = "payslip.env['hr.leave.allocation'].search("
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


def _extract_unit_amount(code):
    """ Le montant UNITAIRE — le taux journalier — extrait VERBATIM de la ligne
    result en base. Il porte le diviseur (/24.0) et le signe : ce script ne les
    reconstruit jamais.

    Deux formes sont acceptées :
      - « result = <unité> * cp_days », ou le produit écrit dans l'autre sens :
        forme en base avant bascule, le facteur cp_days part vers result_qty ;
      - « result = <unité> » accompagnée de « result_qty = cp_days » : forme
        cible, l'unité est déjà isolée — c'est ce qui rend le script idempotent.

    None si la ligne result n'est pas unique, si elle n'est d'aucune des deux
    formes, ou si l'unité isolée référence encore cp_days. """
    lines = _canonical_lines(code)
    matches = [m for m in (_RESULT_RE.match(line) for line in lines) if m]
    if len(matches) != 1:
        return None
    expr = matches[0].group("expr").strip()

    for pattern in (_UNIT_SUFFIX_RE, _UNIT_PREFIX_RE):
        found = pattern.match(expr)
        if found:
            unit = found.group("unit").strip()
            return unit if "cp_days" not in unit else None

    if any(_RESULT_QTY_RE.match(line) for line in lines):
        return expr if "cp_days" not in expr else None
    return None


def _extract_leave_type_term(code):
    """ Le terme « type de congé » du domaine, VERBATIM, ou None s'il n'y en a
    pas exactement un. """
    terms = _LEAVE_TYPE_RE.findall(code or "")
    if len(terms) != 1:
        return None
    return terms[0]


def _is_balance(code):
    return _BALANCE_MARKER in (code or "")


def _is_days_taken(code):
    """ Le corps appartient-il à la famille « jours pris » ? Les deux variantes
    connues sont celles reconnues par 18.0.1.2.16. """
    body = code or ""
    return _LEAVE_MARKER in body or _WORKED_DAYS_MARKER in body


def _check_allocation_model(env):
    """ GARDE-FOU : le modèle et tous les champs lus par le corps cible existent
    bien. Sinon la règle planterait au calcul du bulletin — on préfère ne rien
    écrire. """
    if _ALLOCATION_MODEL not in env:
        _logger.warning(
            "CPALLOC solde STC : le modèle %r est absent de la base — RIEN "
            "N'EST ÉCRIT.", _ALLOCATION_MODEL)
        return False
    fields = env[_ALLOCATION_MODEL]._fields
    missing = [name for name in _ALLOCATION_FIELDS if name not in fields]
    if missing:
        _logger.warning(
            "CPALLOC solde STC : le modèle %r n'expose pas %s — RIEN N'EST "
            "ÉCRIT.", _ALLOCATION_MODEL, ", ".join(missing))
        return False
    return True


def _resolve_structures(env):
    """ Les structures de solde de tout compte, par is_stc.

    Filet de sécurité si le drapeau n'est renseigné nulle part : résolution par
    nom normalisé, avec refus de toute structure qui ne porte pas is_stc quand le
    champ existe. """
    Structure = env["hr.payroll.structure"]
    all_structures = Structure.with_context(active_test=False).search([])

    has_flag = "is_stc" in Structure._fields
    if has_flag:
        structures = all_structures.filtered(lambda s: s.is_stc)
        if structures:
            _logger.info(
                "CPALLOC solde STC : %s structure(s) retenue(s) sur is_stc : %s.",
                len(structures), ", ".join(repr(s.name) for s in structures))
            return structures
        _logger.warning(
            "CPALLOC solde STC : aucune structure ne porte is_stc — repli sur "
            "la résolution par nom.")
    else:
        _logger.warning(
            "CPALLOC solde STC : le champ is_stc est absent de "
            "hr.payroll.structure — repli sur la résolution par nom.")

    by_norm = {}
    for structure in all_structures:
        key = _normalize(structure.name)
        by_norm[key] = by_norm.get(key, Structure) | structure

    structures = Structure
    for struct_name in _FALLBACK_STRUCTURE_NAMES:
        found = by_norm.get(_normalize(struct_name))
        if not found:
            _logger.warning(
                "CPALLOC solde STC : structure %r introuvable, elle est ignorée.",
                struct_name)
            continue
        if len(found) > 1:
            _logger.warning(
                "CPALLOC solde STC : %s structures normalisent vers %r, elles "
                "sont ignorées (désambiguïsation manuelle requise).",
                len(found), struct_name)
            continue
        if has_flag and not found.is_stc:
            _logger.warning(
                "CPALLOC solde STC : la structure %r ne porte pas is_stc, elle "
                "est ignorée — le repli par nom ne doit pas atteindre une "
                "structure de paie régulière.", struct_name)
            continue
        structures |= found

    if structures:
        _logger.info(
            "CPALLOC solde STC : %s structure(s) retenue(s) par nom : %s.",
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


def _find_leave_type_term(env, structure, structures):
    """ Le terme de type de congé, LU EN BASE : d'abord sur les règles CP de la
    structure courante, puis sur celles des autres structures STC. None (+
    warning) si aucune ne le porte. """
    ordered = [structure] + [other for other in structures if other != structure]
    for candidate in ordered:
        for source_code in _DOMAIN_SOURCE_CODES:
            rule = _get_rule(env, candidate, source_code)
            if not rule:
                continue
            term = _extract_leave_type_term(rule.amount_python_compute)
            if not term:
                term = _extract_leave_type_term(rule.condition_python)
            if term:
                _logger.info(
                    "CPALLOC solde STC : terme de type de congé repris de la "
                    "règle %s de %r : %s", source_code, candidate.name, term)
                return term

    _logger.warning(
        "CPALLOC solde STC : aucun terme "
        "('holiday_status_id.work_entry_type_id.code', '=', ...) lisible sur "
        "les règles %s des structures STC — RIEN N'EST ÉCRIT sur %r.",
        " / ".join(_DOMAIN_SOURCE_CODES), structure.name)
    return None


def _build(domain, unit):
    """ (corps, condition) cibles, ou (None, None) si l'un des deux ne compile
    pas. """
    body = _BALANCE_BODY.replace("__DOMAIN__", domain).replace("__UNIT__", unit)
    condition = _BALANCE_CONDITION.replace("__DOMAIN__", domain)
    for source, label in ((body, "amount"), (condition, "condition")):
        try:
            compile(source, "<hr.salary.rule CPALLOC %s>" % label, "exec")
        except SyntaxError:
            _logger.warning(
                "CPALLOC solde STC : le %s cible ne compile pas.\n"
                "--- source ---\n%s", label, source)
            return None, None
    return body, condition


def _apply(env, structures, structure):
    """ Basculer CPALLOC d'une structure STC sur le solde d'allocation. """
    rule = _get_rule(env, structure, _RULE_CODE)
    if not rule:
        _logger.warning(
            "CPALLOC solde STC : règle %s introuvable (ou multiple) sur la "
            "structure %r — rien à corriger.", _RULE_CODE, structure.name)
        return

    current = rule.amount_python_compute

    if not _is_balance(current) and not _is_days_taken(current):
        _logger.warning(
            "CPALLOC solde STC : règle %s de %r — le corps n'est ni sur le "
            "solde d'allocation ni dans la famille « jours pris » (hr.leave ou "
            "worked_days). RIEN N'EST ÉCRIT (revue manuelle requise).\n"
            "--- code en base ---\n%s", _RULE_CODE, structure.name, current)
        return

    # Le montant unitaire est lu sur la structure ELLE-MÊME : il porte le
    # diviseur /24.0 et le signe, que ce script ne réécrit pas.
    unit = _extract_unit_amount(current)
    if not unit:
        _logger.warning(
            "CPALLOC solde STC : règle %s de %r — impossible d'isoler un montant "
            "unitaire depuis la ligne result (forme attendue « result = <unité> "
            "* cp_days », ou « result = <unité> » avec « result_qty = cp_days »). "
            "RIEN N'EST ÉCRIT (revue manuelle requise).\n"
            "--- code en base ---\n%s", _RULE_CODE, structure.name, current)
        return
    _logger.info(
        "CPALLOC solde STC : montant unitaire repris de %r : %s",
        structure.name, unit)

    term = _find_leave_type_term(env, structure, structures)
    if not term:
        return

    body, condition = _build(_ALLOCATION_DOMAIN.replace("__TERM__", term), unit)
    if not body:
        return

    values = {}
    if _normalize_code(current) != _normalize_code(body):
        values["amount_python_compute"] = body
    if _normalize_code(rule.condition_python) != _normalize_code(condition):
        values["condition_python"] = condition

    if not values:
        _logger.info(
            "CPALLOC solde STC : règle %s de %r déjà alimentée par le solde "
            "d'allocation, inchangée.", _RULE_CODE, structure.name)
        return

    previous_body = current
    previous_condition = rule.condition_python
    rule.write(values)
    _logger.info(
        "CPALLOC solde STC : règle %s de %r basculée sur le solde de congés "
        "restant (champs écrits : %s).\n"
        "--- ancien amount_python_compute ---\n%s\n"
        "--- nouveau amount_python_compute ---\n%s\n"
        "--- ancienne condition_python ---\n%s\n"
        "--- nouvelle condition_python ---\n%s",
        _RULE_CODE, structure.name, ", ".join(sorted(values)),
        previous_body, body, previous_condition, condition)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if not _check_allocation_model(env):
        return
    structures = _resolve_structures(env)
    if not structures:
        _logger.warning(
            "CPALLOC solde STC : aucune structure de solde de tout compte "
            "résolue — RIEN N'EST ÉCRIT.")
        return
    for structure in structures:
        _apply(env, structures, structure)
