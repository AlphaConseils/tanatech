# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re
import traceback

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# BASE SALARIALE : la PÉRIODE du bulletin, pas l'état du contrat aujourd'hui.
#
# Bug de fond constaté en production le 23/09/2026. Les règles salariales
# calculent leur base ainsi :
#
#     wages = sum(employee.contract_ids.filtered(
#         lambda c: c.state in ['open', 'open_not_declared']).mapped('wage'))
#
# Le filtre porte sur l'état du contrat AUJOURD'HUI. Le jour où un salarié sort,
# ses contrats passent en 'close' et tous ses bulletins passés perdent ces lignes
# au moindre recalcul.
#
#   RANDRIANIRINA Falisoa Patrick (salarié 2318, contrats 2354 déclaré et 2355
#   NA, clos au 23/09/2026) : au recalcul de son bulletin d'août, sa ligne
#   WORKONPUBLICHOLIDAYS tombe de 4 100 Ar à 0, alors que ses 4,65 heures du
#   15/08 sont toujours dans les entrées de travail.
#
# Même motif que le correctif 1.2.18 sur les heures supplémentaires : un état lu
# au présent pour décider d'un passé.
#
#   avant  wages = sum(employee.contract_ids.filtered(...state...).mapped('wage'))
#   après  wages = payslip.env['hr.payslip'].browse(payslip.id)._tanatech_period_wages()
#
# La méthode vit dans le module (models/hr_payslip.py) : elle somme le contrat du
# bulletin et son contrat JUMEAU (déclaré <-> NA) qui couvrent la période, quel
# que soit leur état hormis 'cancel'. Pour un salarié dont les deux contrats sont
# en cours, le résultat est identique à l'ancienne formule. Un seul contrat par
# catégorie est retenu, le plus récent : deux contrats déclarés successifs (un
# renouvellement en cours de mois) ne sont jamais additionnés.
#
# ---------------------------------------------------------------------------
# LES RÈGLES SONT DÉCOUVERTES, PAS SUPPOSÉES
# ---------------------------------------------------------------------------
# Les corps de règles ne vivent qu'en base, aucun XML du dépôt ne définit de
# hr.salary.rule : impossible de savoir d'ici lesquelles portent le motif. Ce
# script les CHERCHE donc, sur toutes les structures, dans amount_python_compute
# ET dans condition_python, et journalise pour chacune son code, sa structure et
# ses corps avant et après.
#
# Le motif est reconnu par une expression régulière tolérante à la mise en forme
# (espaces, retours à la ligne au milieu de l'expression, guillemets simples ou
# doubles, ordre des deux états, nom de la variable et de la lambda). Ce qu'elle
# n'accepte pas : une autre source que employee.contract_ids, un autre champ que
# 'wage', un troisième état, une condition supplémentaire. Une règle qui porte le
# motif d'état mais dont aucune ligne n'est reconnue déclenche un WARNING avec le
# corps complet et n'est PAS touchée.
#
# ---------------------------------------------------------------------------
# Garde-fous
# ---------------------------------------------------------------------------
#   - la méthode absente du modèle          -> RIEN N'EST ÉCRIT, le module n'est
#     pas à jour ;
#   - « PATTY_BASE » déjà présent           -> déjà migrée, inchangée ;
#   - une ou plusieurs lignes reconnues     -> remplacées, une par une ;
#   - motif présent mais non reconnu        -> WARNING avec le corps complet,
#     RIEN n'est écrit sur cette règle, les autres restent traitées.
# Chaque corps produit est compilé avant écriture, et vérifié sans double
# souligné (safe_eval les refuse). Seuls amount_python_compute et
# condition_python sont écrits. Aucune exception ne remonte au build Odoo.sh.
#
# Pour le rejouer à la main :
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "patty_base", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.26/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.25")
#   env.cr.commit()

_LOG = "PATTY_BASE :"

# La méthode appelée, et le bulletin en enregistrement réel : dans le localdict
# des règles, « payslip » est un objet enveloppe du moteur de paie (voir
# l'en-tête de la migration 18.0.1.2.23).
_METHOD = "_tanatech_period_wages"
_SLIP = "payslip.env['hr.payslip'].browse(payslip.id)"
_MARKER = "PATTY_BASE"
_COMMENT = (
    "  # PATTY_BASE : base salariale de la PÉRIODE du bulletin, "
    "et non l'état du contrat aujourd'hui (correctif 1.2.26)"
)

# Champs de règle susceptibles de porter le motif.
_FIELDS = ["amount_python_compute", "condition_python"]

# Présence du motif d'état, mise en forme mise à part. Sert au REPÉRAGE des
# règles concernées ; la réécriture, elle, passe par _LINE_RE.
_STATE_NEEDLES = [
    "statein['open','open_not_declared']",
    'statein["open","open_not_declared"]',
    "statein['open_not_declared','open']",
    'statein["open_not_declared","open"]',
]

# La ligne de calcul de base, reconnue en entier. Les \\s* autorisent les retours
# à la ligne au milieu de l'expression ; ^ et re.M ancrent le début de ligne pour
# capturer l'indentation d'origine.
_STATES = (
    r"""(?:\[\s*['"]open['"]\s*,\s*['"]open_not_declared['"]\s*\]"""
    r"""|\[\s*['"]open_not_declared['"]\s*,\s*['"]open['"]\s*\])"""
)
_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?P<var>[A-Za-z_]\w*)[ \t]*=[ \t]*"
    r"sum\(\s*employee\s*\.\s*contract_ids\s*\.\s*filtered\(\s*"
    r"lambda\s+(?P<lam>\w+)\s*:\s*(?P=lam)\s*\.\s*state\s+in\s*"
    + _STATES +
    r"\s*\)\s*\.\s*mapped\(\s*['\"]wage['\"]\s*\)\s*\)[ \t]*",
    re.MULTILINE,
)


def _squeeze(code):
    """ Le corps sans aucun blanc : sert à repérer le motif d'état sans se
    laisser piéger par la mise en forme. """
    return "".join((code or "").split())


def _carries_pattern(code):
    squeezed = _squeeze(code)
    return any(needle in squeezed for needle in _STATE_NEEDLES)


def _transform(current):
    """ Le corps cible, ou (None, motif) si le champ ne doit pas être écrit.

    Fonction pure, sans accès à la base : c'est elle que les tests exercent.

    Renvoie (corps, None) quand au moins une ligne a été remplacée,
    (None, None) quand il n'y a rien à faire sur ce champ (pas de motif, ou déjà
    migré), et (None, motif) quand le motif est là mais n'est pas reconnu.
    """
    body = current or ""
    if _MARKER in body:
        return None, None
    if not _carries_pattern(body):
        return None, None

    def _replace(match):
        return "%s%s = %s.%s()%s" % (
            match.group("indent"), match.group("var"), _SLIP, _METHOD, _COMMENT)

    target, count = _LINE_RE.subn(_replace, body)
    if not count:
        return None, (
            "le motif « state in ['open', 'open_not_declared'] » est présent "
            "mais aucune ligne de la forme « <var> = sum(employee.contract_ids"
            ".filtered(lambda c: c.state in [...]).mapped('wage')) » n'a été "
            "reconnue")

    # Le motif ne doit plus rester nulle part : s'il en reste une occurrence,
    # c'est qu'elle sert à autre chose et qu'il faut un oeil humain.
    if _carries_pattern(target):
        return None, (
            "%s ligne(s) de base remplacée(s), mais le motif d'état subsiste "
            "ailleurs dans le corps" % count)

    try:
        compile(target, "<hr.salary.rule>", "exec")
    except SyntaxError as error:
        return None, "le corps réécrit ne compile pas (%s)" % error
    if "__" in target:
        return None, "le corps réécrit contient un double souligné"
    return target, None


def _apply(rule):
    """ Basculer une règle sur la base salariale de la période. """
    structure = rule.struct_id.name or "(sans structure)"
    values = {}
    refused = []

    for field in _FIELDS:
        current = rule[field] or ""
        target, problem = _transform(current)
        if problem:
            refused.append((field, problem, current))
        elif target is not None:
            values[field] = target

    for field, problem, current in refused:
        _logger.warning(
            "%s règle %s de %r (id %s), champ %s : %s. RIEN N'EST ÉCRIT sur ce "
            "champ (revue manuelle requise).\n--- %s en base ---\n%s",
            _LOG, rule.code, structure, rule.id, field, problem, field, current)

    if not values:
        return False

    previous = {field: rule[field] for field in values}
    rule.write(values)
    _logger.info(
        "%s règle %s de %r (id %s, séquence %s) basculée sur la base de la "
        "période (champs : %s).\n%s",
        _LOG, rule.code, structure, rule.id, rule.sequence,
        ", ".join(sorted(values)),
        "\n".join(
            "--- ancien %s ---\n%s\n--- nouveau %s ---\n%s"
            % (field, previous[field], field, values[field])
            for field in sorted(values)))
    return True


def migrate(cr, version):
    try:
        env = api.Environment(cr, SUPERUSER_ID, {})

        if not callable(getattr(env["hr.payslip"], _METHOD, None)):
            _logger.warning(
                "%s le modèle hr.payslip n'expose pas %s : le module n'est pas "
                "à jour, RIEN N'EST ÉCRIT.", _LOG, _METHOD)
            return

        # Les règles ne vivent qu'en base : on les DÉCOUVRE, toutes structures
        # confondues, au lieu de supposer lesquelles portent le motif.
        candidates = env["hr.salary.rule"].with_context(active_test=False).search([])
        concerned = candidates.filtered(
            lambda r: any(_carries_pattern(r[f]) for f in _FIELDS))

        if not concerned:
            _logger.info(
                "%s aucune règle ne porte le motif d'état sur %s règles "
                "examinées : rien à corriger.", _LOG, len(candidates))
            return

        _logger.info(
            "%s %s règle(s) concernée(s) sur %s examinées : %s.",
            _LOG, len(concerned), len(candidates),
            ", ".join("%s de %r (id %s)" % (r.code, r.struct_id.name, r.id)
                      for r in concerned))

        written = 0
        for rule in concerned:
            # Chaque règle est isolée : l'échec de l'une ne prive pas les autres.
            try:
                written += bool(_apply(rule))
            except Exception:
                _logger.warning(
                    "%s échec sur la règle %s (id %s), les autres restent "
                    "traitées.\n%s", _LOG, rule.code, rule.id,
                    traceback.format_exc())

        _logger.info(
            "%s fin : %s règle(s) modifiée(s) sur %s concernée(s).",
            _LOG, written, len(concerned))
    except Exception:
        _logger.warning(
            "%s la migration a échoué, RIEN N'A ÉTÉ GARANTI.\n%s",
            _LOG, traceback.format_exc())
