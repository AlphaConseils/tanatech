# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Prorata de BASIC pour les contrats démarrant en cours de mois.
#
# Défaut : la règle compte les jours CALENDAIRES entre le début du contrat et la
# fin de période, puis divise par 30. Sur un mois de 31 jours, cela produit un
# jour de trop pour tout salarié entrant en cours de mois. Contrat démarrant le
# 04/07/2026 : Odoo compte 28 jours (du 04 au 31), alors qu'un mois normalisé à
# 30 jours en laisse 27 (entrer le 4 fait perdre 3 jours).
#
# L'état de paie du client raisonne en mois de 30 jours (diviseur fixe, colonne
# B = 30 pour tous). Compter sur 31 puis diviser par 30 est incohérent. L'écart
# n'apparaît que les mois de 31 jours ; en février il s'inverserait, en avril les
# deux méthodes coïncident.
#
# ---------------------------------------------------------------------------
# Pourquoi une TRANSFORMATION et non une substitution
# ---------------------------------------------------------------------------
# Les quatre structures n'ont PAS le même corps de BASIC : les deux structures
# « Solde Tout Compte » bornent en plus par contract.date_end. Ce script ne
# compare donc pas à un code cible figé — il reconnaît un MOTIF et le réécrit :
#
#   1. il localise l'unique affectation « nbr_days = <expression> » de premier
#      niveau ;
#   2. il l'enveloppe dans la branche de prorata, en conservant <expression>
#      TELLE QUELLE dans le « else ».
#
# La borne de fin des structures STC est ainsi préservée sans que ce script ait
# besoin de la connaître. Concrètement, sur les structures régulières :
#
#   start = max(contract.date_start, payslip.date_from)
#   nbr_days = min((payslip.date_to - start).days + 1, 30)
#   result = (contract.wage * nbr_days) / 30
#
# devient :
#
#   start = max(contract.date_start, payslip.date_from)
#   if start > payslip.date_from:
#       # Contrat démarrant en cours de mois : prorata sur un mois normalisé
#       # à 30 jours, sans quoi un mois de 31 jours produit un jour de trop.
#       nbr_days = min(30 - (start.day - 1), 30)
#   else:
#       nbr_days = min((payslip.date_to - start).days + 1, 30)
#   result = (contract.wage * nbr_days) / 30
#
# et la variante STC subit la même greffe autour de SON expression, PLUS le
# garde-fou de sortie décrit ci-dessous.
#
# ---------------------------------------------------------------------------
# Borne de sortie, réservée aux corps qui calculent un « end »
# ---------------------------------------------------------------------------
# Un bulletin de solde de tout compte est par définition celui d'un sortant. Les
# deux structures STC posent déjà end = min(contract.date_end, payslip.date_to) ;
# il suffit donc que le prorata d'entrée respecte cette borne. Sans cela, entré
# le 04/07 et parti le 15/07, le salarié serait payé 27 jours au lieu de 12. La
# branche de prorata reçoit donc, sur ces corps uniquement :
#
#   nbr_days = min(nbr_days, (end - start).days + 1)
#
# Le critère d'ajout est la présence d'une AFFECTATION de « end » dans le corps
# (indentée ou non), pas le nom de la structure ni la mention de
# contract.date_end. Les structures régulières ne calculent pas de « end », ne
# reçoivent donc pas cette borne, et leur inversion de février reste intacte.
#
# ---------------------------------------------------------------------------
# Indentation
# ---------------------------------------------------------------------------
# La ligne « nbr_days = ... » n'est pas toujours de premier niveau : sur
# « Solde Tout Compte - NA » elle vit dans un else (« if end < start: result = 0.0
# else: nbr_days = ... »). Son indentation est donc capturée et le bloc greffé
# s'aligne dessus, l'expression conservée étant enfoncée d'un cran de plus.
#
# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------
# Le motif n'est reconnu que si TOUTES ces conditions tiennent :
#   - une seule affectation « nbr_days = ... » de premier niveau (une ligne
#     indentée, ou plusieurs affectations, font échouer la reconnaissance) ;
#   - une affectation de « start » la précède ;
#   - le code réécrit est syntaxiquement valide (compilation vérifiée avant
#     écriture).
# Un corps déjà proratisé est reconnu et laissé tel quel. Tout corps qui ne
# rentre dans aucun des deux cas déclenche un WARNING avec le code complet, et
# RIEN n'est écrit sur cette structure — les autres restent traitées.
#
# Seul amount_python_compute est écrit. Le code remplacé est journalisé en INFO,
# structure par structure, avec le nouveau code en regard.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "basic_prorata", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.12/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.11")
#   env.cr.commit()

_RULE_CODE = "BASIC"

# Structures visées, résolues par nom NORMALISÉ (casse / accents / ponctuation),
# jamais par id : la production utilise des variantes de libellé et les ids
# divergent entre environnements.
_TARGET_STRUCTURES = [
    "Paie Régulière",
    "Paie Régulière NA",
    "Solde Tout Compte",
    "Solde Tout Compte - NA",
]

# Bloc greffé au-dessus de l'affectation existante. L'expression d'origine est
# réinjectée, indentée, dans le « else » — elle n'est jamais réécrite.
_PRORATA_HEAD = [
    "if start > payslip.date_from:",
    "    # Contrat démarrant en cours de mois : prorata sur un mois normalisé",
    "    # à 30 jours, sans quoi un mois de 31 jours produit un jour de trop.",
    "    nbr_days = min(30 - (start.day - 1), 30)",
]

# Borne de sortie, ajoutée aux SEULS corps qui calculent une variable « end »
# (les deux « Solde Tout Compte », qui posent end = min(contract.date_end,
# payslip.date_to)). Sans elle, un contrat qui démarre ET se termine dans la
# période verrait le prorata d'entrée dépasser la période réellement due : un
# salarié entré le 4 et parti le 15 serait payé 27 jours au lieu de 12. Les
# structures régulières ne définissent pas de « end » et ne la reçoivent pas —
# leur inversion de février doit rester intacte.
_END_BOUND = [
    "    # Le prorata d'entrée ne doit pas dépasser la période réellement due :",
    "    # sur un solde de tout compte, le contrat se termine dans la période.",
    "    nbr_days = min(nbr_days, (end - start).days + 1)",
]

_PRORATA_ELSE = ["else:"]

# Affectation de nbr_days. L'indentation de tête est CAPTURÉE : sur la structure
# « Solde Tout Compte - NA » la ligne vit dans un else (« if end < start: ...
# else: nbr_days = ... »), et le bloc greffé doit s'aligner dessus.
_NBR_DAYS_RE = re.compile(r"^(?P<indent>[ \t]*)nbr_days\s*=\s*(?P<expr>\S.*)$")
# Affectation de start, indentée ou non.
_START_RE = re.compile(r"^[ \t]*start\s*=\s*\S")
# Affectation d'une variable « end », indentée ou non : c'est la présence de
# cette borne dans LE CORPS — et non le nom de la structure — qui commande
# l'ajout de la borne de sortie.
_END_ASSIGN_RE = re.compile(r"^[ \t]*end\s*=\s*\S")

# Marqueurs du code déjà proratisé.
_PRORATA_MARKERS = ["start > payslip.date_from", "start.day"]


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


def _already_prorated(code):
    """ True si le corps porte déjà la branche de prorata. """
    return all(marker in (code or "") for marker in _PRORATA_MARKERS)


def _defines_end(lines):
    """ True si le corps calcule une variable « end » (bornage de fin de
    période). C'est ce critère — et non le nom de la structure — qui commande
    l'ajout de la borne de sortie dans la branche de prorata. """
    return any(_END_ASSIGN_RE.match(line) for line in lines)


def _transform(code):
    """ Le corps réécrit avec la branche de prorata, ou None si le motif n'est
    pas reconnu (auquel cas l'appelant n'écrit rien).

    L'expression de nbr_days est conservée VERBATIM dans le « else », et le bloc
    greffé est aligné sur l'indentation de la ligne d'origine — sur la structure
    « Solde Tout Compte - NA », cette ligne vit dans un else. Les corps qui
    calculent un « end » reçoivent en plus, dans la branche de prorata, la borne
    qui empêche le prorata d'entrée de dépasser la période réellement due. """
    lines = _canonical_lines(code)

    matches = [(i, _NBR_DAYS_RE.match(line)) for i, line in enumerate(lines)]
    positions = [(i, match) for i, match in matches if match]
    if len(positions) != 1:
        return None
    position, match = positions[0]

    if not any(_START_RE.match(line) for line in lines[:position]):
        return None

    block = list(_PRORATA_HEAD)
    if _defines_end(lines):
        block += _END_BOUND
    block += _PRORATA_ELSE

    # Le bloc est réindenté au niveau de l'affectation d'origine, et
    # l'expression conservée est enfoncée d'un cran de plus, dans le « else ».
    indent = match.group("indent")
    expression = match.group("expr")
    grafted = [indent + line for line in block]
    grafted.append("%s    nbr_days = %s" % (indent, expression))

    rewritten = "\n".join(lines[:position] + grafted + lines[position + 1:])

    # Filet : on n'écrit jamais un corps qui ne compile pas.
    try:
        compile(rewritten, "<hr.salary.rule BASIC>", "exec")
    except SyntaxError:
        return None
    return rewritten


def _resolve_structures(env):
    """ { nom de référence -> hr.payroll.structure } pour les structures visées.

    Une clé normalisée peut collisionner sur plusieurs structures : dans ce cas
    on ne devine pas, on saute (désambiguïsation manuelle). """
    Structure = env["hr.payroll.structure"]

    structures_by_norm = {}
    for structure in Structure.with_context(active_test=False).search([]):
        key = _normalize(structure.name)
        structures_by_norm[key] = structures_by_norm.get(key, Structure) | structure

    resolved = {}
    for struct_name in _TARGET_STRUCTURES:
        structure = structures_by_norm.get(_normalize(struct_name))
        if not structure:
            _logger.warning(
                "BASIC : structure de paie %r introuvable, elle est ignorée.",
                struct_name)
            continue
        if len(structure) > 1:
            _logger.warning(
                "BASIC : %s structures de paie normalisent vers %r, elles sont "
                "ignorées (désambiguïsation manuelle requise).",
                len(structure), struct_name)
            continue
        resolved[struct_name] = structure
    return resolved


def _prorate_basic(env, structures):
    """ Greffer la branche de prorata sur la règle BASIC de chaque structure, là
    où le motif est reconnu et le corps pas déjà proratisé. """
    Rule = env["hr.salary.rule"]

    for struct_name, structure in structures.items():
        rules = Rule.with_context(active_test=False).search([
            ("struct_id", "=", structure.id),
            ("code", "=", _RULE_CODE),
        ])
        if not rules:
            _logger.warning(
                "BASIC : aucune règle de code %r sur la structure %r — rien à "
                "proratiser.", _RULE_CODE, struct_name)
            continue

        for rule in rules:
            current = rule.amount_python_compute

            if _already_prorated(current):
                _logger.info(
                    "BASIC : règle de %r déjà proratisée, inchangée.", struct_name)
                continue

            rewritten = _transform(current)
            if rewritten is None:
                _logger.warning(
                    "BASIC : règle de %r — motif non reconnu (il faut une unique "
                    "affectation « nbr_days = ... » de premier niveau, précédée "
                    "d'une affectation de « start »). RIEN N'EST ÉCRIT sur cette "
                    "structure (revue manuelle requise).\n--- code en base ---\n%s",
                    struct_name, current)
                continue

            rule.write({"amount_python_compute": rewritten})
            _logger.info(
                "BASIC : prorata greffé sur la structure %r.\n"
                "--- ancien code remplacé ---\n%s\n--- nouveau code ---\n%s",
                struct_name, current, rewritten)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structures = _resolve_structures(env)
    _prorate_basic(env, structures)
