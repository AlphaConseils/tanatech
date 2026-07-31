# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def _normalize(label):
    import unicodedata, re
    s = unicodedata.normalize('NFKD', label or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^0-9a-zA-Z]+', ' ', s).strip().lower()
    return s


# ---------------------------------------------------------------------------
# Rule code bodies (stored verbatim as amount_python_compute / condition_python)
# ---------------------------------------------------------------------------

# hr.leave domain, inserted literally in the "Paie Régulière" rules.
_LEAVE_DOM = (
    "[('employee_id', '=', employee.id), "
    "('state', '=', 'validate'), "
    "('holiday_status_id.work_entry_type_id.code', '=', 'LEAVE120'), "
    "('request_date_from', '<=', payslip.date_to), "
    "('request_date_to', '>=', payslip.date_from)]"
)

# ---- 'Paie Régulière NA' : source = worked_days (LEAVE120) ----
_WD_CONDITION = (
    "result = bool(worked_days.get('LEAVE120') "
    "and worked_days.get('LEAVE120').number_of_days)"
)
_WD_DED_AMOUNT = (
    "cp_days = worked_days.get('LEAVE120').number_of_days\n"
    "result = -(contract.wage / 30.0) * cp_days"
)
_WD_ALLOC_AMOUNT = (
    "cp_days = worked_days.get('LEAVE120').number_of_days\n"
    "result = (contract.wage / 24.0) * cp_days"
)

# ---- 'Paie Régulière' : source = hr.leave ----
_LEAVE_CONDITION = "result = bool(payslip.env['hr.leave'].search_count(%s))" % _LEAVE_DOM
_LEAVE_PREFIX = "\n".join([
    "cp_days = 0.0",
    "for l in payslip.env['hr.leave'].search(%s):" % _LEAVE_DOM,
    "    if l.request_date_from >= payslip.date_from and l.request_date_to <= payslip.date_to:",
    "        cp_days += l.number_of_days",
    "    else:",
    "        start = max(l.request_date_from, payslip.date_from)",
    "        stop = min(l.request_date_to, payslip.date_to)",
    "        span = (l.request_date_to - l.request_date_from).days + 1",
    "        cp_days += l.number_of_days * ((stop - start).days + 1) / span",
])
_LEAVE_DED_AMOUNT = _LEAVE_PREFIX + "\nresult = -(contract.wage / 30.0) * cp_days"
_LEAVE_ALLOC_AMOUNT = _LEAVE_PREFIX + "\nresult = (contract.wage / 24.0) * cp_days"


def _rule_specs():
    """ Rules to codify, grouped by exact structure name. Same names, sequences,
    categories and flags on both structures; only the data source differs
    (worked_days for the NA structure, hr.leave for the declared one). """
    return {
        'Paie Régulière NA': [
            {
                'code': 'CPDED',
                'name': "Déduction jours de congés payés",
                'sequence': 1200,
                'category_code': 'ABS',
                'condition_python': _WD_CONDITION,
                'amount_python_compute': _WD_DED_AMOUNT,
            },
            {
                'code': 'CPALLOC',
                'name': "Allocation congés payés",
                'sequence': 1210,
                'category_code': 'PRIME',
                'condition_python': _WD_CONDITION,
                'amount_python_compute': _WD_ALLOC_AMOUNT,
            },
        ],
        'Paie Régulière': [
            {
                'code': 'CPDED',
                'name': "Déduction jours de congés payés",
                'sequence': 1200,
                'category_code': 'ABS',
                'condition_python': _LEAVE_CONDITION,
                'amount_python_compute': _LEAVE_DED_AMOUNT,
            },
            {
                'code': 'CPALLOC',
                'name': "Allocation congés payés",
                'sequence': 1210,
                'category_code': 'PRIME',
                'condition_python': _LEAVE_CONDITION,
                'amount_python_compute': _LEAVE_ALLOC_AMOUNT,
            },
        ],
    }


def _get_category(env, code, _cache):
    """ hr.salary.rule.category by exact code, cached; None (+warning) if the
    category is missing or ambiguous. """
    if code in _cache:
        return _cache[code]
    categories = env['hr.salary.rule.category'].search([('code', '=', code)])
    if len(categories) != 1:
        _logger.warning(
            "CP rules migration: salary rule category with code %r not found "
            "(or multiple), rules requiring it are skipped.", code)
        _cache[code] = None
    else:
        _cache[code] = categories
    return _cache[code]


def _create_cp_salary_rules(env):
    """ VOLET 1 — create the paid-leave deduction/allocation salary rules on the
    two structures, only where they are missing (idempotent). """
    Rule = env['hr.salary.rule']
    Structure = env['hr.payroll.structure']
    category_cache = {}

    # Index of every structure by its normalized name, so the target labels are
    # matched despite case / accent / separator differences (e.g. the production
    # 'Paie régulière NA' vs the coded 'Paie Régulière NA'). Several structures
    # can collapse onto the same normalized key: keep them all and skip that key.
    structures_by_norm = {}
    for structure in Structure.with_context(active_test=False).search([]):
        structures_by_norm.setdefault(_normalize(structure.name), Structure)
        structures_by_norm[_normalize(structure.name)] |= structure

    for struct_name, rules in _rule_specs().items():
        structure = structures_by_norm.get(_normalize(struct_name))
        if not structure:
            _logger.warning(
                "CP rules migration: payroll structure %r not found, its "
                "rules are skipped.", struct_name)
            continue
        if len(structure) > 1:
            _logger.warning(
                "CP rules migration: %s payroll structures normalize to %r, "
                "its rules are skipped (manual disambiguation required).",
                len(structure), struct_name)
            continue

        for spec in rules:
            existing = Rule.search_count([
                ('struct_id', '=', structure.id),
                ('code', '=', spec['code']),
            ])
            if existing:
                continue
            category = _get_category(env, spec['category_code'], category_cache)
            if not category:
                continue
            Rule.create({
                'name': spec['name'],
                'code': spec['code'],
                'sequence': spec['sequence'],
                'category_id': category.id,
                'struct_id': structure.id,
                'condition_select': 'python',
                'condition_python': spec['condition_python'],
                'amount_select': 'code',
                'amount_python_compute': spec['amount_python_compute'],
                'appears_on_payslip': True,
            })
            _logger.info(
                "CP rules migration: created rule %s on structure %r.",
                spec['code'], struct_name)


def _create_print_server_actions(env):
    """ VOLET 2 — codify the two list-view print server actions where they are
    missing. Guard by (name, model_id) so production instances that already
    hold them (created without an external id) are left untouched. """
    model = env['ir.model'].search([('model', '=', 'hr.payslip')], limit=1)
    if not model:
        _logger.warning(
            "CP rules migration: model hr.payslip not found, print server "
            "actions are skipped.")
        return

    actions = [
        {
            'name': "Imprimer les bulletins (A4)",
            'code': "action = records.action_print_payslip()",
        },
        {
            'name': "Imprimer les tickets (NA)",
            'code': "action = records.action_print_nd_tickets()",
        },
    ]
    ServerAction = env['ir.actions.server']
    for action in actions:
        existing = ServerAction.search_count([
            ('name', '=', action['name']),
            ('model_id', '=', model.id),
        ])
        if existing:
            continue
        ServerAction.create({
            'name': action['name'],
            'model_id': model.id,
            'binding_model_id': model.id,
            'binding_view_types': 'list',
            'state': 'code',
            'code': action['code'],
        })
        _logger.info(
            "CP rules migration: created server action %r.", action['name'])


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _create_cp_salary_rules(env)
    _create_print_server_actions(env)
