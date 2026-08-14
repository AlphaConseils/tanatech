# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Correction de la formule de prorata livrée en 18.0.1.2.12.
#
# L'état de paie du client applique « 30 - jour d'entrée », et non
# « 30 - (jour d'entrée - 1) ». Un contrat démarrant le 04 vaut 26 jours chez le
# client, là où la formule livrée en 1.2.12 en compte 27 :
#
#   jour d'entrée   1.2.12   client (cible)
#         04         27 j        26 j
#         09         22 j        21 j
#         17         14 j        13 j
#
# Ce script ne touche donc QUE l'expression de la branche de prorata :
#
#   nbr_days = min(30 - (start.day - 1), 30)        ->  livré en 1.2.12
#   nbr_days = max(min(30 - start.day, 30), 0)      ->  cible
#
# Le plancher à zéro n'est pas décoratif : « 30 - start.day » devient NÉGATIF le
# 31 d'un mois de 31 jours (30 - 31 = -1), ce qui produirait un BASIC négatif —
# une anomalie qui resterait invisible jusqu'à sortir un bulletin aberrant.
# L'expression de 1.2.12 plafonnait à zéro par construction (30 - (31 - 1) = 0),
# la nouvelle doit le faire explicitement. La borne de sortie des structures STC
# ne rattrape pas ce cas : min(-1, ...) reste à -1.
#
#   jour d'entrée   29     30     31
#   sans plancher    1 j    0 j   -1 j
#   avec plancher    1 j    0 j    0 j
#
# Tout le reste du corps est laissé strictement intact : la détection du motif,
# l'indentation, la borne de sortie des structures STC
# (« nbr_days = min(nbr_days, (end - start).days + 1) ») et l'expression
# d'origine réinjectée dans le « else » ont été posées par 18.0.1.2.12 et ne sont
# pas retouchées ici. Une seule ligne change par structure.
#
# ---------------------------------------------------------------------------
# Reconnaissance
# ---------------------------------------------------------------------------
# Le corps attendu en base est celui produit par 18.0.1.2.12. La ligne visée est
# repérée à la comparaison, blancs ignorés, ce qui la retrouve quelle que soit
# son indentation — de premier niveau sur trois structures, enfoncée de deux
# crans sur « Solde Tout Compte - NA » où elle vit dans un else. L'indentation
# trouvée est réutilisée telle quelle.
#
# Trois issues par structure :
#   - une ligne porte l'ancienne expression   -> elle seule est réécrite ;
#   - aucune ancienne, mais la cible présente -> déjà corrigé, on ne touche pas ;
#   - tout autre cas                          -> WARNING avec le code complet et
#     RIEN n'est écrit sur cette structure ; les autres restent traitées.
#
# Le troisième cas couvre notamment une structure sur laquelle 18.0.1.2.12
# n'aurait pas abouti : elle porte encore son code d'origine, sans branche de
# prorata. Le WARNING est alors le bon signal — c'est 18.0.1.2.12 qu'il faut
# reprendre sur cette structure, pas ce script.
#
# Seul amount_python_compute est écrit. Le code remplacé est journalisé en INFO,
# structure par structure.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "basic_formule", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.13/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.12")
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

# Expression livrée en 18.0.1.2.12, à remplacer.
_OLD_EXPRESSION = "nbr_days = min(30 - (start.day - 1), 30)"
# Expression cible, alignée sur l'état de paie du client, plancher à zéro inclus.
_NEW_EXPRESSION = "nbr_days = max(min(30 - start.day, 30), 0)"


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


def _squeeze(text):
    """ Forme sans aucun blanc, pour comparer une expression indépendamment de
    son indentation et de ses espaces internes. """
    return re.sub(r"\s+", "", text or "")


def _indent_of(line):
    return line[:len(line) - len(line.lstrip())]


def _swap_expression(code):
    """ Le corps avec la seule ligne de prorata réécrite, ou None si l'ancienne
    expression n'y figure pas exactement une fois. """
    lines = _canonical_lines(code)
    old = _squeeze(_OLD_EXPRESSION)

    positions = [i for i, line in enumerate(lines) if _squeeze(line) == old]
    if len(positions) != 1:
        return None
    position = positions[0]

    # L'indentation d'origine est réutilisée : sur « Solde Tout Compte - NA »
    # la ligne est enfoncée de deux crans, dans un else.
    lines[position] = _indent_of(lines[position]) + _NEW_EXPRESSION
    rewritten = "\n".join(lines)

    # Filet : on n'écrit jamais un corps qui ne compile pas.
    try:
        compile(rewritten, "<hr.salary.rule BASIC>", "exec")
    except SyntaxError:
        return None
    return rewritten


def _already_corrected(code):
    """ True si le corps porte déjà l'expression cible. """
    new = _squeeze(_NEW_EXPRESSION)
    return any(_squeeze(line) == new for line in _canonical_lines(code))


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
                "BASIC formule : structure de paie %r introuvable, elle est "
                "ignorée.", struct_name)
            continue
        if len(structure) > 1:
            _logger.warning(
                "BASIC formule : %s structures de paie normalisent vers %r, "
                "elles sont ignorées (désambiguïsation manuelle requise).",
                len(structure), struct_name)
            continue
        resolved[struct_name] = structure
    return resolved


def _fix_expression(env, structures):
    """ Remplacer l'expression de prorata sur la règle BASIC de chaque structure,
    là où l'ancienne expression est présente et pas déjà corrigée. """
    Rule = env["hr.salary.rule"]

    for struct_name, structure in structures.items():
        rules = Rule.with_context(active_test=False).search([
            ("struct_id", "=", structure.id),
            ("code", "=", _RULE_CODE),
        ])
        if not rules:
            _logger.warning(
                "BASIC formule : aucune règle de code %r sur la structure %r — "
                "rien à corriger.", _RULE_CODE, struct_name)
            continue

        for rule in rules:
            current = rule.amount_python_compute
            rewritten = _swap_expression(current)

            if rewritten is None:
                if _already_corrected(current):
                    _logger.info(
                        "BASIC formule : règle de %r déjà sur l'expression "
                        "cible, inchangée.", struct_name)
                    continue
                _logger.warning(
                    "BASIC formule : règle de %r — l'expression livrée en "
                    "18.0.1.2.12 n'y figure pas exactement une fois, et "
                    "l'expression cible non plus. RIEN N'EST ÉCRIT sur cette "
                    "structure (revue manuelle requise : 18.0.1.2.12 a-t-elle "
                    "abouti ici ?).\n--- code en base ---\n%s",
                    struct_name, current)
                continue

            rule.write({"amount_python_compute": rewritten})
            _logger.info(
                "BASIC formule : prorata aligné sur l'état de paie client "
                "(30 - jour d'entrée) sur la structure %r.\n"
                "--- ancien code remplacé ---\n%s\n--- nouveau code ---\n%s",
                struct_name, current, rewritten)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structures = _resolve_structures(env)
    _fix_expression(env, structures)
