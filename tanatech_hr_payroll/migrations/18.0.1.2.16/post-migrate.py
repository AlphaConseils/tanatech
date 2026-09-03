# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Décompte des jours de congés payés en jours CALENDAIRES, sur les quatre
# structures, pour les règles CPDED et CPALLOC.
#
# Défaut : le client compte les congés en jours calendaires, week-ends compris,
# là où Odoo compte les jours ouvrés. Un congé du 16 au 29 juillet vaut 14 jours
# chez le client et 10 dans Odoo. Le client fait référence.
#
# Deux familles de corps coexistent en base, et la correction diffère :
#
#   « Paie Régulière » et « Solde Tout Compte »  -> source hr.leave
#       cp_days est accumulé depuis l.number_of_days, qui compte les jours
#       OUVRÉS. Seul le décompte change ; le domaine de recherche et la ligne
#       result sont conservés tels quels.
#
#   « Paie Régulière NA » et « Solde Tout Compte - NA » -> source worked_days
#       cp_days = worked_days.get('LEAVE120').number_of_days, un scalaire déjà
#       agrégé sur les jours porteurs d'une entrée de travail — donc ouvrés lui
#       aussi, et SANS aucune date d'où dériver un calendaire. Ces structures
#       basculent donc sur la méthode hr.leave : corps ET condition sont repris
#       de leur structure déclarée de même niveau, seule leur ligne result
#       propre étant conservée.
#
# Correspondance des sources (une structure NA emprunte à sa déclarée de même
# niveau, jamais à l'autre étage) :
#
#   Paie Régulière           -> elle-même
#   Paie Régulière NA        -> Paie Régulière
#   Solde Tout Compte        -> elle-même
#   Solde Tout Compte - NA   -> Solde Tout Compte
#
# Corps cible, pour les quatre :
#
#   cp_days = 0.0
#   for l in payslip.env['hr.leave'].search(<domaine repris à l'identique>):
#       # Jours calendaires, week-ends compris, conformément à la méthode client.
#       start = max(l.request_date_from, payslip.date_from)
#       stop = min(l.request_date_to, payslip.date_to)
#       cp_days += (stop - start).days + 1
#   <ligne result propre à la structure>
#
# Le prorata des congés à cheval sur deux mois disparaît : on compte directement
# les jours de chevauchement, ce qui est plus juste que d'appliquer un ratio
# calendaire à un nombre de jours ouvrés.
#
# ---------------------------------------------------------------------------
# Ce que le script LIT plutôt que de le reconstruire
# ---------------------------------------------------------------------------
# Trois éléments ne sont jamais réécrits de mémoire :
#   - le DOMAINE de recherche, extrait de la ligne « for l in ... .search(...) »
#     du corps source ;
#   - la CONDITION des structures NA, copiée verbatim depuis la règle de même
#     code de leur structure source ;
#   - la ligne RESULT, extraite du corps PROPRE à chaque structure — jamais
#     déduite de la structure jumelle, car elle diffère entre CPDED (/30.0,
#     négatif) et CPALLOC (/24.0, positif) et peut différer entre structures.
#
# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------
# Par règle et par structure :
#   - corps déjà en décompte calendaire      -> inchangé ;
#   - corps reconnu (hr.leave ou worked_days) et ligne result unique extraite,
#     domaine et condition source disponibles -> réécriture ;
#   - tout autre cas                          -> WARNING avec le code complet et
#     RIEN n'est écrit sur cette règle ; les autres restent traitées.
# La condition source doit elle-même référencer hr.leave, sans quoi les
# structures qui en dépendent sont sautées : on ne propage pas une condition
# worked_days sur une structure qu'on bascule justement vers hr.leave.
#
# Le corps réécrit est compilé avant écriture. Seuls amount_python_compute et,
# pour les structures NA, condition_python sont écrits. Séquence, catégorie et
# appears_on_payslip ne sont pas touchés. L'ancien code est journalisé en INFO.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "cp_calendaire", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.16/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.15")
#   env.cr.commit()

_RULE_CODES = ["CPDED", "CPALLOC"]

# Structure -> structure dont on emprunte le domaine et la condition. Résolution
# par nom NORMALISÉ (casse / accents / ponctuation), jamais par id.
_SOURCE_OF = [
    ("Paie Régulière", "Paie Régulière"),
    ("Paie Régulière NA", "Paie Régulière"),
    ("Solde Tout Compte", "Solde Tout Compte"),
    ("Solde Tout Compte - NA", "Solde Tout Compte"),
]

# Corps cible : %s reçoit le domaine, la ligne result est ajoutée ensuite.
_CALENDAR_BODY = "\n".join([
    "cp_days = 0.0",
    "for l in payslip.env['hr.leave'].search(%s):",
    "    # Jours calendaires, week-ends compris, conformément à la méthode client.",
    "    start = max(l.request_date_from, payslip.date_from)",
    "    stop = min(l.request_date_to, payslip.date_to)",
    "    cp_days += (stop - start).days + 1",
])

# Ligne de boucle d'où le domaine est extrait.
_SEARCH_RE = re.compile(
    r"^for\s+l\s+in\s+payslip\.env\['hr\.leave'\]\.search\((?P<domain>.+)\)\s*:\s*$")
# Ligne result de premier niveau.
_RESULT_RE = re.compile(r"^result\s*=\s*\S.*$")
# Marqueur du décompte calendaire déjà en place.
_CALENDAR_MARKER = "cp_days += (stop - start).days + 1"
# Marqueurs de famille.
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


def _extract_domain(code):
    """ Le domaine de la recherche hr.leave, tel quel, ou None s'il n'y a pas
    exactement une ligne de boucle reconnaissable. """
    matches = [_SEARCH_RE.match(line) for line in _canonical_lines(code)]
    matches = [m for m in matches if m]
    if len(matches) != 1:
        return None
    return matches[0].group("domain")


def _extract_result_line(code):
    """ La ligne result de premier niveau, VERBATIM, ou None s'il n'y en a pas
    exactement une. Elle est propre à chaque règle : /30.0 négatif pour CPDED,
    /24.0 positif pour CPALLOC. """
    lines = [line for line in _canonical_lines(code) if _RESULT_RE.match(line)]
    if len(lines) != 1:
        return None
    return lines[0]


def _is_calendar(code):
    return _CALENDAR_MARKER in (code or "")


def _is_recognised(code):
    """ Le corps appartient-il à l'une des deux familles connues ? """
    body = code or ""
    return _LEAVE_MARKER in body or _WORKED_DAYS_MARKER in body


def _build_body(domain, result_line):
    """ Le corps cible, ou None s'il ne compile pas. """
    body = (_CALENDAR_BODY % domain) + "\n" + result_line
    try:
        compile(body, "<hr.salary.rule CP>", "exec")
    except SyntaxError:
        return None
    return body


def _resolve_structures(env):
    """ { nom de référence -> hr.payroll.structure } pour les structures visées.

    Une clé normalisée peut collisionner sur plusieurs structures : dans ce cas
    on ne devine pas, on saute (désambiguïsation manuelle). """
    Structure = env["hr.payroll.structure"]

    by_norm = {}
    for structure in Structure.with_context(active_test=False).search([]):
        key = _normalize(structure.name)
        by_norm[key] = by_norm.get(key, Structure) | structure

    resolved = {}
    for struct_name in {name for name, _ in _SOURCE_OF} | {s for _, s in _SOURCE_OF}:
        structure = by_norm.get(_normalize(struct_name))
        if not structure:
            _logger.warning(
                "CP calendaire : structure de paie %r introuvable.", struct_name)
            continue
        if len(structure) > 1:
            _logger.warning(
                "CP calendaire : %s structures de paie normalisent vers %r, "
                "elles sont ignorées (désambiguïsation manuelle requise).",
                len(structure), struct_name)
            continue
        resolved[struct_name] = structure
    return resolved


def _get_rule(env, structure, rule_code):
    """ La règle (struct_id, code), ou None si absente ou multiple. """
    rules = env["hr.salary.rule"].with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("code", "=", rule_code),
    ])
    if len(rules) != 1:
        return None
    return rules


def _read_sources(env, structures, rule_code):
    """ { nom de structure source -> (domaine, condition) }, lus EN BASE.

    Le domaine et la condition ne sont jamais reconstruits : ils sont extraits
    du corps réellement présent sur la structure source. """
    sources = {}
    for source_name in {source for _, source in _SOURCE_OF}:
        structure = structures.get(source_name)
        if not structure:
            continue
        rule = _get_rule(env, structure, rule_code)
        if not rule:
            _logger.warning(
                "CP calendaire : règle %s introuvable (ou multiple) sur la "
                "structure source %r — les structures qui en dépendent sont "
                "sautées.", rule_code, source_name)
            continue

        domain = _extract_domain(rule.amount_python_compute)
        if not domain:
            _logger.warning(
                "CP calendaire : impossible d'extraire le domaine hr.leave de "
                "la règle %s de %r — les structures qui en dépendent sont "
                "sautées.\n--- code en base ---\n%s",
                rule_code, source_name, rule.amount_python_compute)
            continue

        condition = rule.condition_python or ""
        if _LEAVE_MARKER.rstrip("(") not in condition:
            _logger.warning(
                "CP calendaire : la condition de la règle %s de %r ne référence "
                "pas hr.leave — elle n'est pas propagée, les structures NA qui "
                "en dépendent sont sautées.\n--- condition en base ---\n%s",
                rule_code, source_name, condition)
            continue

        sources[source_name] = (domain, condition)
    return sources


def _apply(env, structures, rule_code):
    """ Réécrire CPDED ou CPALLOC sur les quatre structures. """
    sources = _read_sources(env, structures, rule_code)

    for struct_name, source_name in _SOURCE_OF:
        structure = structures.get(struct_name)
        if not structure:
            continue

        rule = _get_rule(env, structure, rule_code)
        if not rule:
            _logger.warning(
                "CP calendaire : règle %s introuvable (ou multiple) sur la "
                "structure %r — rien à corriger.", rule_code, struct_name)
            continue

        current = rule.amount_python_compute
        source = sources.get(source_name)
        if not source:
            _logger.warning(
                "CP calendaire : source %r indisponible pour la règle %s de %r "
                "— RIEN N'EST ÉCRIT sur cette règle.",
                source_name, rule_code, struct_name)
            continue
        domain, condition = source

        # La ligne result est lue sur la structure ELLE-MÊME, jamais empruntée.
        result_line = _extract_result_line(current)
        if not result_line:
            _logger.warning(
                "CP calendaire : règle %s de %r — impossible d'isoler une ligne "
                "result unique de premier niveau. RIEN N'EST ÉCRIT (revue "
                "manuelle requise).\n--- code en base ---\n%s",
                rule_code, struct_name, current)
            continue

        if not _is_calendar(current) and not _is_recognised(current):
            _logger.warning(
                "CP calendaire : règle %s de %r — le corps n'appartient à "
                "aucune des deux familles connues (hr.leave ou worked_days). "
                "RIEN N'EST ÉCRIT (revue manuelle requise).\n"
                "--- code en base ---\n%s", rule_code, struct_name, current)
            continue

        target_body = _build_body(domain, result_line)
        if not target_body:
            _logger.warning(
                "CP calendaire : règle %s de %r — le corps réécrit ne compile "
                "pas. RIEN N'EST ÉCRIT.\n--- domaine extrait ---\n%s",
                rule_code, struct_name, domain)
            continue

        values = {}
        if _normalize_code(current) != _normalize_code(target_body):
            values["amount_python_compute"] = target_body
        if _normalize_code(rule.condition_python) != _normalize_code(condition):
            values["condition_python"] = condition

        if not values:
            _logger.info(
                "CP calendaire : règle %s de %r déjà en décompte calendaire, "
                "inchangée.", rule_code, struct_name)
            continue

        previous_body = current
        previous_condition = rule.condition_python
        rule.write(values)
        _logger.info(
            "CP calendaire : règle %s de %r alignée sur le décompte calendaire "
            "(champs écrits : %s).\n"
            "--- ancien amount_python_compute ---\n%s\n"
            "--- nouveau amount_python_compute ---\n%s\n"
            "--- ancienne condition_python ---\n%s\n"
            "--- nouvelle condition_python ---\n%s",
            rule_code, struct_name, ", ".join(sorted(values)),
            previous_body, target_body, previous_condition, condition)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structures = _resolve_structures(env)
    for rule_code in _RULE_CODES:
        _apply(env, structures, rule_code)
