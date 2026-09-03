# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Retour arrière sur le correctif MATOFF de 18.0.1.2.10.
#
# 18.0.1.2.10 avait neutralisé l'abattement de maternité sur la structure NON
# AFFECTÉE, au motif que le non affecté n'ouvre droit à aucune indemnité CNaPS et
# que la moitié retenue n'y serait donc compensée par personne.
#
# Cette lecture est infirmée par le fichier client, vérifié sur les deux cas
# réels des deux sociétés : l'abattement de 50 % y est appliqué sur les DEUX
# bulletins, pas seulement sur le déclaré.
#
#   STUDYDAS / HERINIRINA        salaire non affecté 700 000 -> fichier 350 000
#   MASONTSIKA / RAZAFINDRAVELO  salaire 609 200             -> fichier 304 600
#
# Dans les deux cas la valeur du fichier vaut exactement la moitié du salaire.
# L'Excel fait foi : ce script rétablit le code d'origine.
#
#   result = 0                                  ->  livré en 1.2.10
#   if worked_days.get("MATOFF"):                   cible (retour au code
#       result = -( contract.wage / 2)              d'origine, espace après la
#   else:                                           parenthèse compris)
#       result = 0
#
# PÉRIMÈTRE — ce script ne touche QUE la structure non affectée. La structure
# déclarée conserve la proratisation livrée en 18.0.1.2.11, qui reste valable :
# l'abattement y est légitime, seule sa répartition au prorata des jours y a été
# corrigée. Les deux libellés normalisent d'ailleurs vers des clés DISTINCTES,
# la structure déclarée ne peut donc pas être atteinte par erreur.
#
# ---------------------------------------------------------------------------
# Reconnaissance
# ---------------------------------------------------------------------------
# Comparaison canonique du corps entier, en trois branches :
#   - code == code cible (celui d'origine)  -> déjà rétabli, on ne touche pas ;
#   - code == « result = 0 » de 1.2.10      -> on réécrit ;
#   - tout autre code                       -> WARNING avec le code complet et
#     RIEN n'est écrit. Une règle retouchée à la main entre-temps, ou une
#     structure sur laquelle 18.0.1.2.10 ne s'est pas appliquée, ne doit pas
#     être écrasée à l'aveugle.
#
# Seul amount_python_compute est écrit. Séquence, catégorie et
# appears_on_payslip ne sont pas touchés. Le code remplacé est journalisé en
# INFO.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "matoff_forfait", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.15/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.14")
#   env.cr.commit()

_RULE_CODE = "MATOFF"

# Structure visée, résolue par nom NORMALISÉ (casse / accents / ponctuation),
# jamais par id. « Paie Régulière » et « Paie Régulière NA » normalisent vers des
# clés distinctes : la structure déclarée est hors d'atteinte de ce script.
_TARGET_STRUCTURE = "Paie Régulière NA"

# Code livré en 18.0.1.2.10, à remplacer.
_OLD_AMOUNT = "result = 0"

# Code cible : celui d'origine, reproduit au caractère près — l'espace après la
# parenthèse ouvrante de « -( contract.wage / 2) » en fait partie.
_TARGET_AMOUNT = "\n".join([
    'if worked_days.get("MATOFF"):',
    '    result = -( contract.wage / 2)',
    'else:',
    '    result = 0',
])


def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation, pour apparier les libellés de structures entre environnements. """
    import unicodedata
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
            "MATOFF NA : structure de paie %r introuvable, retour arrière sauté.",
            struct_name)
        return None
    if len(matches) > 1:
        _logger.warning(
            "MATOFF NA : %s structures de paie normalisent vers %r, retour "
            "arrière sauté (désambiguïsation manuelle requise).",
            len(matches), struct_name)
        return None
    return matches


def _restore_matoff(env, structure):
    """ Rétablir l'abattement forfaitaire d'un demi-mois, et uniquement là où le
    code en base est bien celui livré par 18.0.1.2.10. """
    Rule = env["hr.salary.rule"]
    target = _normalize_code(_TARGET_AMOUNT)
    neutralized = _normalize_code(_OLD_AMOUNT)

    rules = Rule.with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("code", "=", _RULE_CODE),
    ])
    if not rules:
        _logger.warning(
            "MATOFF NA : aucune règle de code %r sur la structure %r — rien à "
            "rétablir.", _RULE_CODE, structure.name)
        return

    for rule in rules:
        current = _normalize_code(rule.amount_python_compute)

        if current == target:
            _logger.info(
                "MATOFF NA : règle de %r déjà sur l'abattement forfaitaire, "
                "inchangée.", structure.name)
            continue

        if current != neutralized:
            _logger.warning(
                "MATOFF NA : règle de %r — le code en base ne correspond ni au "
                "code cible ni au %r livré en 18.0.1.2.10. RIEN N'EST ÉCRIT "
                "(revue manuelle requise).\n--- code en base ---\n%s",
                structure.name, _OLD_AMOUNT, rule.amount_python_compute)
            continue

        previous = rule.amount_python_compute
        rule.write({"amount_python_compute": _TARGET_AMOUNT})
        _logger.info(
            "MATOFF NA : abattement forfaitaire d'un demi-mois rétabli sur la "
            "structure %r (le fichier client l'applique sur les deux "
            "bulletins).\n--- ancien code remplacé ---\n%s\n"
            "--- nouveau code ---\n%s",
            structure.name, previous, _TARGET_AMOUNT)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structure = _resolve_structure(env, _TARGET_STRUCTURE)
    if not structure:
        return
    _restore_matoff(env, structure)
