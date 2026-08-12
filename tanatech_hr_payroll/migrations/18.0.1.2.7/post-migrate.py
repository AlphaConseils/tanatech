# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Correctif de la catégorie testée par les règles IRSA02 et IRSA03 de la
# structure « Paie Régulière ».
#
# Les deux règles testent categories.get("IRSA"). Cette catégorie N'EXISTE PAS
# en base : seules IRSA01, IRSA02 et IRSA03 y sont définies. Le test renvoie donc
# toujours None, la condition « > 3000 » échoue, et le résultat retombe
# systématiquement sur le minimum de perception de 3 000 Ar. Conséquence : le
# barème progressif malgache calculé par IRSA01 n'est jamais appliqué. Constaté
# en production sur un salarié à 889 000 Ar de brut déclaré — IRSA01 calcule
# 81 700 Ar, IRSA02 applique 3 000 Ar.
#
# Le correctif remplace "IRSA" par "IRSA01" dans les deux règles. Le code cible
# est exactement celui déjà en place sur la structure « Solde Tout Compte », qui
# est correcte et n'est PAS touchée par ce script.
#
# Périmètre : structure « Paie Régulière » uniquement, règles IRSA02 et IRSA03.
# Les structures non affectées n'ont pas de règles IRSA.
#
# Prudence sur l'écriture — comparaison canonique en TROIS branches :
#   - code == code cible      -> déjà corrigé, on ne touche pas ;
#   - code == code défectueux -> on réécrit ;
#   - tout autre code         -> WARNING, on ne touche PAS. Une règle
#     retouchée à la main entre-temps ne doit pas être écrasée à l'aveugle.
# Seul amount_python_compute est écrit. Le code remplacé est journalisé en INFO
# pour rester récupérable.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "irsa", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.7/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.6")
#   env.cr.commit()

# Structure visée, résolue par nom NORMALISÉ (casse / accents / ponctuation),
# jamais par id : les ids divergent entre environnements.
_TARGET_STRUCTURE = "Paie Régulière"

# Règles visées, résolues par (struct_id, code), jamais par id de règle.
_TARGET_RULE_CODES = ["IRSA02", "IRSA03"]

# Code défectueux attendu en base (catégorie inexistante "IRSA").
_DEFECTIVE_AMOUNT = "\n".join([
    'if((categories.get("IRSA") or 0))>3000:',
    '    result = ((categories.get("IRSA") or 0)) - (categories.get("CHILD") or 0)',
    'else:',
    '   result = 3000',
])

# Code cible, repris à l'identique de la structure « Solde Tout Compte ».
_TARGET_AMOUNT = "\n".join([
    'if((categories.get("IRSA01") or 0))>3000:',
    '    result = ((categories.get("IRSA01") or 0)) - (categories.get("CHILD") or 0)',
    'else:',
    '   result = 3000',
])


def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation, pour apparier les libellés de structures entre environnements. """
    import unicodedata
    import re
    s = unicodedata.normalize("NFKD", label or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-zA-Z]+", " ", s).strip().lower()
    return s


def _normalize_code(code):
    """ Forme canonique d'un corps de règle : fins de ligne unifiées, blancs de
    fin supprimés, lignes vides de tête/queue ignorées. L'indentation de tête est
    PRÉSERVÉE — elle est signifiante en Python. """
    lines = (code or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def _resolve_structure(env, struct_name):
    """ La structure de paie désignée, ou None (+ warning) si absente ou si
    plusieurs structures normalisent vers le même libellé. """
    Structure = env["hr.payroll.structure"]

    matches = Structure
    for structure in Structure.with_context(active_test=False).search([]):
        if _normalize(structure.name) == _normalize(struct_name):
            matches |= structure

    if not matches:
        _logger.warning(
            "IRSA : structure de paie %r introuvable, correctif sauté.",
            struct_name)
        return None
    if len(matches) > 1:
        _logger.warning(
            "IRSA : %s structures de paie normalisent vers %r, correctif sauté "
            "(désambiguïsation manuelle requise).", len(matches), struct_name)
        return None
    return matches


def _fix_irsa_rules(env, structure):
    """ Remplacer la catégorie testée (IRSA -> IRSA01) sur IRSA02 et IRSA03, et
    uniquement là où le code en base est bien le code défectueux connu. """
    Rule = env["hr.salary.rule"]
    target = _normalize_code(_TARGET_AMOUNT)
    defective = _normalize_code(_DEFECTIVE_AMOUNT)

    for rule_code in _TARGET_RULE_CODES:
        rules = Rule.with_context(active_test=False).search([
            ("struct_id", "=", structure.id),
            ("code", "=", rule_code),
        ])
        if not rules:
            _logger.warning(
                "IRSA : aucune règle de code %r sur la structure %r — rien à "
                "corriger.", rule_code, structure.name)
            continue

        for rule in rules:
            current = _normalize_code(rule.amount_python_compute)

            if current == target:
                _logger.info(
                    "IRSA : règle %s de %r déjà sur le code cible, inchangée.",
                    rule_code, structure.name)
                continue

            if current != defective:
                _logger.warning(
                    "IRSA : règle %s de %r — le code en base ne correspond ni "
                    "au code cible ni au code défectueux attendu. RIEN N'EST "
                    "ÉCRIT (revue manuelle requise).\n"
                    "--- code en base ---\n%s",
                    rule_code, structure.name, rule.amount_python_compute)
                continue

            previous = rule.amount_python_compute
            rule.write({"amount_python_compute": _TARGET_AMOUNT})
            _logger.info(
                "IRSA : règle %s de %r corrigée (IRSA -> IRSA01).\n"
                "--- ancien code remplacé ---\n%s\n--- nouveau code ---\n%s",
                rule_code, structure.name, previous, _TARGET_AMOUNT)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structure = _resolve_structure(env, _TARGET_STRUCTURE)
    if not structure:
        return
    _fix_irsa_rules(env, structure)
