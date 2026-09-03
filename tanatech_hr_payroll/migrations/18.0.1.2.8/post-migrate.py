# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Rattachement du type d'entrée AVASP « Avance spéciale » à la structure
# « Paie Régulière ».
#
# Défaut : la structure ne déclare qu'un seul type d'entrée, LIC02 (ajouté en
# 18.0.1.2.5). AVASP n'y figure pas, alors qu'il est déjà rattaché à la structure
# non affectée.
#
# Or sept fiches de paie régulière portent actuellement un input AVASP, pour
# 393 000 Ar au total. Ces inputs ont été saisis à la main : au prochain
# compute_sheet sur ces fiches ils seront SUPPRIMÉS sans erreur ni avertissement,
# _compute_input_line_ids régénérant input_line_ids depuis les types déclarés sur
# la structure. Le rattachement pérennise cette saisie.
#
# Le placement est volontaire et correct : ces sept salariés ont un contrat non
# affecté à salaire nul, leur déduction d'achat interne ne peut donc s'imputer
# que sur le bulletin déclaré.
#
# La règle salariale AVASP existe déjà sur la structure (séquence 7000, catégorie
# AJUST) : elle n'est ni créée ni modifiée ici, seul le rattachement du TYPE
# manque. Le type d'entrée lui-même est réutilisé, jamais recréé — un doublon de
# code casserait inputs.get('AVASP').
#
# Même mécanisme que le rattachement de LIC02 en 18.0.1.2.5 : commande de lien
# (4, id) uniquement, les types déjà déclarés sur la structure sont préservés.
# Enregistrement écrit en ORM sans external ID, donc hors du périmètre de
# rechargement des données du module : il survit aux upgrades sans dépendre d'un
# noupdate.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "avasp", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.8/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.7")
#   env.cr.commit()

_INPUT_TYPE_CODE = "AVASP"

# Structure visée, résolue par nom NORMALISÉ (casse / accents / ponctuation),
# jamais par id : les ids divergent entre environnements.
_TARGET_STRUCTURE = "Paie Régulière"


def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation, pour apparier les libellés de structures entre environnements. """
    import unicodedata
    import re
    s = unicodedata.normalize("NFKD", label or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-zA-Z]+", " ", s).strip().lower()
    return s


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
            "AVASP : structure de paie %r introuvable, rattachement sauté.",
            struct_name)
        return None
    if len(matches) > 1:
        _logger.warning(
            "AVASP : %s structures de paie normalisent vers %r, rattachement "
            "sauté (désambiguïsation manuelle requise).", len(matches), struct_name)
        return None
    return matches


def _get_input_type(env):
    """ Le type d'entrée AVASP EXISTANT (celui de la structure non affectée). On
    n'en crée jamais un second : un doublon de code casserait inputs.get('AVASP'). """
    input_types = env["hr.payslip.input.type"].with_context(
        active_test=False).search([("code", "=", _INPUT_TYPE_CODE)])
    if not input_types:
        _logger.warning(
            "AVASP : aucun type d'entrée de code %r en base — rattachement "
            "sauté (le type doit préexister).", _INPUT_TYPE_CODE)
        return None
    if len(input_types) > 1:
        _logger.warning(
            "AVASP : %s types d'entrée portent le code %r — rattachement sauté "
            "(désambiguïsation manuelle requise).",
            len(input_types), _INPUT_TYPE_CODE)
        return None
    return input_types


def _link_input_type(env, structure):
    """ Ajouter AVASP à input_line_type_ids de la structure, sans toucher aux
    types déjà rattachés (commande de lien, jamais de remplacement de liste). """
    input_type = _get_input_type(env)
    if not input_type:
        return

    Structure = env["hr.payroll.structure"]
    # input_line_type_ids (structure) et struct_ids (type d'entrée) sont les deux
    # faces du même many2many ; on écrit sur celle qui existe réellement.
    if "input_line_type_ids" in Structure._fields:
        if input_type in structure.input_line_type_ids:
            _logger.info(
                "AVASP : type d'entrée déjà rattaché à %r, inchangé.",
                structure.name)
            return
        structure.write({"input_line_type_ids": [(4, input_type.id)]})
        _logger.info(
            "AVASP : type d'entrée rattaché à la structure %r.", structure.name)
        return

    if structure in input_type.struct_ids:
        _logger.info(
            "AVASP : type d'entrée déjà rattaché à %r, inchangé.", structure.name)
        return
    input_type.write({"struct_ids": [(4, structure.id)]})
    _logger.info(
        "AVASP : type d'entrée rattaché à la structure %r.", structure.name)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    structure = _resolve_structure(env, _TARGET_STRUCTURE)
    if not structure:
        return
    _link_input_type(env, structure)
