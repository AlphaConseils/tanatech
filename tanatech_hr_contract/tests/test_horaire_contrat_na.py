# -*- coding: utf-8 -*-
""" Changement d'horaire d'un contrat déclaré en cours, pour un salarié qui a un
contrat NA miroir et un congé validé (1.8).

Avant la correction, hr_holidays_contract plantait (KeyError
'open_not_declared') en triant les contrats qui chevauchent le congé.

hr.contract.write fait un cr.commit() après chaque propagation au NA : il est
neutralisé ici, sans quoi le test validerait ses données en base.
"""
import unittest
from datetime import date

from odoo import Command
from odoo.tests.common import TransactionCase, tagged

SILENCIEUX = {
    'tracking_disable': True,
    'mail_create_nolog': True,
    'mail_notrack': True,
    'no_reset_password': True,
}


@tagged('post_install', '-at_install')
class TestHoraireContratNA(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.structure_type = cls.env['hr.payroll.structure.type'].search([], limit=1)
        if not cls.structure_type:
            raise unittest.SkipTest("Aucun type de structure de paie en base.")
        cls.calendar_a = cls._calendar('Horaire test NA (A)', 17.0)
        cls.calendar_b = cls._calendar('Horaire test NA (B)', 16.0)
        cls.employee = cls.env['hr.employee'].with_company(cls.company).with_context(**SILENCIEUX).create({
            'name': 'Salarié Test Horaire NA', 'company_id': cls.company.id,
            'resource_calendar_id': cls.calendar_a.id, 'tz': 'Indian/Antananarivo'})
        cls.leave_type = cls.env['hr.leave.type'].with_company(cls.company).with_context(**SILENCIEUX).create({
            'name': 'Congé test horaire NA', 'company_id': cls.company.id,
            'requires_allocation': 'no', 'leave_validation_type': 'no_validation', 'request_unit': 'day'})

    @classmethod
    def _calendar(cls, name, hour_to):
        lines = []
        for day in '012345':
            lines += [Command.create({'name': 'Matin', 'dayofweek': day, 'hour_from': 8.0, 'hour_to': 12.0,
                                      'day_period': 'morning'}),
                      Command.create({'name': 'Après-midi', 'dayofweek': day, 'hour_from': 13.0, 'hour_to': hour_to,
                                      'day_period': 'afternoon'})]
        return cls.env['resource.calendar'].with_context(**SILENCIEUX).create({
            'name': name, 'company_id': cls.company.id, 'tz': 'Indian/Antananarivo',
            'attendance_ids': [Command.clear()] + lines})

    def setUp(self):
        super().setUp()
        self.patch(self.env.cr, 'commit', lambda *args, **kwargs: None)

    def test_changement_horaire_avec_na_et_conge_valide(self):
        # Parcours métier : contrat déclaré créé en brouillon puis passé en cours
        # (le NA miroir est créé par copy()), congé validé, puis changement
        # d'horaire du contrat déclaré depuis la fiche contrat.
        sd = self.env['hr.contract'].with_company(self.company).with_context(**SILENCIEUX).create({
            'name': 'Contrat test horaire NA', 'employee_id': self.employee.id, 'company_id': self.company.id,
            'date_start': date(2026, 1, 1), 'wage': 300000.0, 'family_allowance': 0.0, 'state': 'draft',
            'contract_category': 'declared', 'structure_type_id': self.structure_type.id,
            'resource_calendar_id': self.calendar_a.id})
        sd.with_context(**SILENCIEUX).write({'state': 'open'})
        self.env.invalidate_all()
        na = self.env['hr.contract'].search([('contract_id', '=', sd.id), ('contract_category', '=', 'not_declared')])
        self.assertEqual((len(na), na.state), (1, 'open_not_declared'))

        leave = self.env['hr.leave'].with_context(leave_skip_state_check=True, **SILENCIEUX).create({
            'name': 'Congé test horaire NA', 'employee_id': self.employee.id,
            'holiday_status_id': self.leave_type.id,
            'request_date_from': date(2026, 11, 9), 'request_date_to': date(2026, 11, 13)})
        self.assertEqual(leave.state, 'validate')
        self.assertNotIn(na, leave._get_overlapping_contracts(),
                         "le NA ne doit pas compter parmi les contrats qui chevauchent le congé")

        # Le changement d'horaire plantait ici (KeyError 'open_not_declared').
        sd.with_context(**SILENCIEUX).write({'resource_calendar_id': self.calendar_b.id})

        self.env.invalidate_all()                 # le NA est mis à jour en SQL brut
        self.assertEqual(sd.resource_calendar_id, self.calendar_b)
        self.assertEqual(na.resource_calendar_id, self.calendar_b)
        self.assertEqual(self.employee.resource_calendar_id, self.calendar_b)
        self.assertEqual(leave.state, 'validate')
        self.assertEqual(leave.resource_calendar_id, self.calendar_b)
