# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import re

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Création des règles CPDED et CPALLOC sur les structures SOLDE TOUT COMPTE.
#
# Défaut : les deux structures de solde de tout compte n'ont ni CPDED (déduction
# des jours de congés payés pris) ni CPALLOC (allocation des congés acquis). Un
# salarié sortant ne peut donc pas voir ses congés traités sur son STC, alors que
# c'est précisément le bulletin où le solde doit être apuré.
#
# Les deux règles sont des copies conformes de celles des structures régulières,
# créées par la migration 18.0.1.1.10 :
#   - « Solde Tout Compte »      <- copie de « Paie Régulière »     (variante SD,
#     recherche directe sur hr.leave, avec prorata des congés à cheval) ;
#   - « Solde Tout Compte - NA » <- copie de « Paie Régulière NA »  (variante NA,
#     source worked_days LEAVE120).
# condition_python et amount_python_compute sont LUS EN BASE sur la règle source
# au moment de l'exécution, jamais recopiés en dur ici : si les corps ont été
# ajustés depuis 1.1.10, la copie reste conforme. Séquence et catégorie sont en
# revanche fixées par ce script :
#   - CPDED   : séquence 1200, catégorie ABS   (montant négatif, déduction) ;
#   - CPALLOC : séquence 1210, catégorie PRIME (montant positif, allocation).
#
# GARDE-FOU — sur les structures STC le brut est calculé par GROSS et non par
# TOTAL01. Si ABS et PRIME n'entrent pas dans le brut, les deux règles
# s'afficheraient sur le bulletin sans effet ni sur le net ni sur les
# cotisations. Ce script VÉRIFIE donc, structure par structure, que ces deux
# catégories sont bien agrégées, et NE CRÉE RIEN sur une structure qui échoue —
# un WARNING est émis avec le code complet de GROSS pour arbitrage manuel.
#
# La chaîne d'agrégation diffère d'une structure STC à l'autre, ce qui impose de
# résoudre UN niveau d'indirection (les deux cas constatés en base) :
#   - « Solde Tout Compte - NA » : GROSS somme directement ABS et PRIME ;
#   - « Solde Tout Compte »      : GROSS ne somme que TOTAL01, et c'est TOTAL01
#     qui agrège ABS et PRIME. La chaîne est complète, en deux étages.
# La vérification procède donc en deux temps : d'abord les catégories citées
# directement par GROSS, puis, pour celles qui manquent encore, les corps des
# règles DE MÊME CODE que les catégories que GROSS somme, sur la MÊME structure.
# On ne descend pas au-delà. Le chemin retenu (« direct » ou « via TOTAL01 ») est
# journalisé pour que la décision soit lisible dans les logs.
#
# La vérification reste textuelle et volontairement stricte : en cas de doute
# elle échoue (donc ne crée rien) plutôt que de créer des règles inopérantes.
#
# Idempotence : garde sur (struct_id, code), une règle déjà présente n'est ni
# recréée ni réécrite. Aucune règle existante n'est modifiée par ce script — il
# ne fait que créer ce qui manque. Enregistrements créés en ORM sans external ID,
# donc hors du périmètre de rechargement des données du module.
#
# Ce script n'est PAS joué automatiquement sur les builds Odoo.sh de production :
# il y est lancé à la main en shell, après merge de la PR, via
#   import importlib.util, odoo
#   spec = importlib.util.spec_from_file_location(
#       "cp_stc", "/home/odoo/src/user/tanatech_hr_payroll/"
#       "migrations/18.0.1.2.9/post-migrate.py")
#   mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
#   mod.migrate(env.cr, "18.0.1.2.8")
#   env.cr.commit()

_GROSS_CODE = "GROSS"

# Catégories que GROSS doit agréger pour que les règles aient un effet.
_REQUIRED_CATEGORIES = ["ABS", "PRIME"]

# Règles à copier : code -> (séquence, code de catégorie).
_RULE_SPECS = [
    ("CPDED", 1200, "ABS"),
    ("CPALLOC", 1210, "PRIME"),
]

# (structure source, structure cible). Résolues par nom NORMALISÉ (casse /
# accents / ponctuation), jamais par id : la production utilise des variantes de
# libellé et les ids divergent entre environnements.
_STRUCTURE_PAIRS = [
    ("Paie Régulière", "Solde Tout Compte"),
    ("Paie Régulière NA", "Solde Tout Compte - NA"),
]

# Champs recopiés tels quels depuis la règle source.
_COPIED_FIELDS = [
    "name",
    "condition_select",
    "condition_python",
    "amount_select",
    "amount_python_compute",
    "appears_on_payslip",
]


def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation, pour apparier les libellés de structures entre environnements. """
    import unicodedata
    s = unicodedata.normalize("NFKD", label or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-zA-Z]+", " ", s).strip().lower()
    return s


def _index_structures(env):
    """ { clé normalisée -> recordset des structures portant ce nom }. """
    Structure = env["hr.payroll.structure"]
    by_norm = {}
    for structure in Structure.with_context(active_test=False).search([]):
        key = _normalize(structure.name)
        by_norm[key] = by_norm.get(key, Structure) | structure
    return by_norm


def _resolve(by_norm, struct_name, role):
    """ La structure désignée, ou None (+ warning) si absente ou ambiguë. """
    structure = by_norm.get(_normalize(struct_name))
    if not structure:
        _logger.warning(
            "CP STC : structure %s %r introuvable, la paire est sautée.",
            role, struct_name)
        return None
    if len(structure) > 1:
        _logger.warning(
            "CP STC : %s structures normalisent vers %r (%s), la paire est "
            "sautée (désambiguïsation manuelle requise).",
            len(structure), struct_name, role)
        return None
    return structure


def _mentions(body, category_code):
    """ True si le corps de règle référence le code de catégorie sous forme de
    littéral entre guillemets. """
    return bool(re.search(r"""["']%s["']""" % re.escape(category_code), body or ""))


def _referenced_category_codes(body):
    """ Codes de catégorie lus par un corps de règle via categories.get("XXX").

    Sert à suivre UN niveau d'indirection : sur « Solde Tout Compte », GROSS ne
    somme que TOTAL01, qui agrège lui-même ABS et PRIME. """
    pattern = r"""categories\s*\.\s*get\s*\(\s*["']([0-9A-Za-z_]+)["']"""
    return set(re.findall(pattern, body or ""))


def _gross_aggregates_categories(env, structure):
    """ GARDE-FOU : True seulement si les catégories requises entrent bien dans
    le brut, soit directement dans GROSS, soit via UNE règle intermédiaire que
    GROSS somme. Au-delà d'un niveau, ou en cas de doute -> False, et rien ne
    sera créé sur cette structure. """
    rules = env["hr.salary.rule"].with_context(active_test=False).search([
        ("struct_id", "=", structure.id),
        ("code", "=", _GROSS_CODE),
    ])
    if not rules:
        _logger.warning(
            "CP STC : aucune règle %s sur la structure %r — impossible de "
            "vérifier que le brut agrège %s. RIEN N'EST CRÉÉ sur cette "
            "structure.", _GROSS_CODE, structure.name,
            " et ".join(_REQUIRED_CATEGORIES))
        return False
    if len(rules) > 1:
        _logger.warning(
            "CP STC : %s règles %s sur la structure %r — vérification du brut "
            "impossible. RIEN N'EST CRÉÉ sur cette structure.",
            len(rules), _GROSS_CODE, structure.name)
        return False

    gross_body = rules.amount_python_compute or ""

    # NIVEAU 1 — les catégories requises sont référencées directement par GROSS.
    covered_by = {
        category: _GROSS_CODE
        for category in _REQUIRED_CATEGORIES
        if _mentions(gross_body, category)
    }
    if len(covered_by) == len(_REQUIRED_CATEGORIES):
        _logger.info(
            "CP STC : structure %r — chemin « %s direct » : le brut agrège "
            "directement %s. Création autorisée.\n--- code de %s ---\n%s",
            structure.name, _GROSS_CODE, " et ".join(_REQUIRED_CATEGORIES),
            _GROSS_CODE, gross_body)
        return True

    # NIVEAU 2 — un seul niveau d'indirection. GROSS peut ne sommer qu'une
    # catégorie intermédiaire (cas réel : « Solde Tout Compte », dont GROSS vaut
    # categories.get("TOTAL01") et dont TOTAL01 agrège ABS et PRIME). Pour chaque
    # catégorie référencée par GROSS, on cherche la règle DE MÊME CODE sur la
    # MÊME structure et on inspecte son corps. On ne descend pas plus bas.
    Rule = env["hr.salary.rule"].with_context(active_test=False)
    for intermediate_code in sorted(_referenced_category_codes(gross_body)):
        if intermediate_code == _GROSS_CODE:
            continue  # auto-référence : on ne se relit pas soi-même
        still_missing = [
            category for category in _REQUIRED_CATEGORIES
            if category not in covered_by
        ]
        if not still_missing:
            break

        intermediate = Rule.search([
            ("struct_id", "=", structure.id),
            ("code", "=", intermediate_code),
        ])
        if len(intermediate) != 1:
            continue
        intermediate_body = intermediate.amount_python_compute or ""
        for category in still_missing:
            if _mentions(intermediate_body, category):
                covered_by[category] = intermediate_code

    missing = [c for c in _REQUIRED_CATEGORIES if c not in covered_by]
    if missing:
        _logger.warning(
            "CP STC : structure %r — %s %s pas agrégée%s dans le brut, ni "
            "directement par %s ni par une règle intermédiaire qu'il somme "
            "(un seul niveau d'indirection est résolu). Les règles CPDED / "
            "CPALLOC s'y afficheraient SANS entrer dans le brut (aucun effet "
            "sur le net ni sur les cotisations). RIEN N'EST CRÉÉ sur cette "
            "structure — arbitrage manuel requis.\n--- code de %s ---\n%s",
            structure.name, " et ".join(missing),
            "ne sont" if len(missing) > 1 else "n'est",
            "s" if len(missing) > 1 else "",
            _GROSS_CODE, _GROSS_CODE, gross_body)
        return False

    path = ", ".join(
        "%s via %s" % (category, covered_by[category])
        if covered_by[category] != _GROSS_CODE
        else "%s direct" % category
        for category in _REQUIRED_CATEGORIES
    )
    _logger.info(
        "CP STC : structure %r — chemin retenu : %s. Le brut agrège bien %s, "
        "création autorisée.\n--- code de %s ---\n%s",
        structure.name, path, " et ".join(_REQUIRED_CATEGORIES), _GROSS_CODE,
        gross_body)
    return True


def _get_category(env, category_code, cache):
    """ hr.salary.rule.category par code, mise en cache ; None (+ warning) si
    absente ou ambiguë. """
    if category_code in cache:
        return cache[category_code]
    categories = env["hr.salary.rule.category"].search([
        ("code", "=", category_code),
    ])
    if len(categories) != 1:
        _logger.warning(
            "CP STC : catégorie de règle salariale de code %r introuvable ou "
            "multiple (%s trouvée(s)) — les règles qui en dépendent sont "
            "sautées.", category_code, len(categories))
        cache[category_code] = None
    else:
        cache[category_code] = categories
    return cache[category_code]


def _copy_rules(env, source, target, category_cache):
    """ Créer sur `target` les règles CP manquantes, en recopiant le corps de la
    règle homonyme de `source`. Résolution par (struct_id, code), jamais par id. """
    Rule = env["hr.salary.rule"]

    for rule_code, sequence, category_code in _RULE_SPECS:
        existing = Rule.with_context(active_test=False).search_count([
            ("struct_id", "=", target.id),
            ("code", "=", rule_code),
        ])
        if existing:
            _logger.info(
                "CP STC : règle %s déjà présente sur %r, inchangée.",
                rule_code, target.name)
            continue

        source_rules = Rule.with_context(active_test=False).search([
            ("struct_id", "=", source.id),
            ("code", "=", rule_code),
        ])
        if not source_rules:
            _logger.warning(
                "CP STC : règle source %s introuvable sur %r — rien à copier "
                "vers %r.", rule_code, source.name, target.name)
            continue
        if len(source_rules) > 1:
            _logger.warning(
                "CP STC : %s règles %s sur la structure source %r — copie vers "
                "%r sautée (désambiguïsation manuelle requise).",
                len(source_rules), rule_code, source.name, target.name)
            continue

        category = _get_category(env, category_code, category_cache)
        if not category:
            continue

        values = {field: source_rules[field] for field in _COPIED_FIELDS}
        values.update({
            "code": rule_code,
            "sequence": sequence,
            "category_id": category.id,
            "struct_id": target.id,
        })
        Rule.create(values)
        _logger.info(
            "CP STC : règle %s créée sur %r (séquence %s, catégorie %s), "
            "copiée depuis %r.",
            rule_code, target.name, sequence, category_code, source.name)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    by_norm = _index_structures(env)
    category_cache = {}

    for source_name, target_name in _STRUCTURE_PAIRS:
        source = _resolve(by_norm, source_name, "source")
        target = _resolve(by_norm, target_name, "cible")
        if not source or not target:
            continue
        if not _gross_aggregates_categories(env, target):
            continue
        _copy_rules(env, source, target, category_cache)
