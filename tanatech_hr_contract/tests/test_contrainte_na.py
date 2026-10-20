# -*- coding: utf-8 -*-
""" Contrainte « un seul contrat à la fois » et contrats NA miroirs (1.7).

Un contrat NA et SON contrat déclaré (lié par contract_id) se chevauchent par
construction : ils ne doivent pas s'opposer. Face à tout autre contrat du
salarié (un autre contrat déclaré, ou un autre NA), le contrôle reste entier.

Les contrats sont créés directement dans leur état final : hr.contract.write
fait un cr.commit() sur les changements d'état (synchronisation du miroir NA),
ce qui casserait le point de sauvegarde du test.
"""
import unittest
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged

SILENCIEUX = {
    'tracking_disable': True,
    'mail_create_nolog': True,
    'mail_notrack': True,
    'no_reset_password': True,
}


@tagged('post_install', '-at_install')
class TestContrainteNA(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.structure_type = cls.env['hr.payroll.structure.type'].search([], limit=1)
        if not cls.structure_type:
            raise unittest.SkipTest("Aucun type de structure de paie en base.")
        cls.employee = cls.env['hr.employee'].with_company(cls.company).with_context(
            **SILENCIEUX).create({'name': 'Salarié Test Contrainte NA', 'company_id': cls.company.id})

    def _contract(self, category, state, start, end=False, source=None, name=None):
        return self.env['hr.contract'].with_company(self.company).with_context(**SILENCIEUX).create({
            'name': name or 'Test contrainte NA (%s %s)' % (category, start),
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'date_start': start,
            'date_end': end,
            'wage': 100000.0,
            'family_allowance': 0.0,
            'state': state,
            'contract_category': category,
            'structure_type_id': self.structure_type.id,
            'contract_id': source.id if source else False,
        })

    def test_na_clos_face_a_son_contrat_declare_accepte(self):
        """Le cas des tests g de tanatech_hr_payroll : un salarié sorti, ses
        contrats déclaré et NA clos sur les mêmes dates, NA créé par l'ORM."""
        sd = self._contract('declared', 'close', date(2026, 1, 1), date(2026, 9, 23))
        na = self._contract('not_declared', 'close', date(2026, 1, 1), date(2026, 9, 23), source=sd)
        self.assertEqual((sd.state, na.state), ('close', 'close'))
        self.assertEqual(na.contract_id, sd)

    def test_na_en_cours_face_a_son_contrat_declare_accepte(self):
        sd = self._contract('declared', 'open', date(2026, 1, 1))
        na = self._contract('not_declared', 'open_not_declared', date(2026, 1, 1), source=sd)
        self.assertEqual(na.contract_id, sd)

    def test_deux_na_chevauchants_refuses(self):
        """Deux NA du même salarié qui se chevauchent restent refusés, même
        rattachés au même contrat déclaré."""
        sd = self._contract('declared', 'close', date(2026, 1, 1), date(2026, 9, 30))
        self._contract('not_declared', 'close', date(2026, 1, 1), date(2026, 9, 30), source=sd)
        with self.assertRaises(ValidationError):
            self._contract('not_declared', 'close', date(2026, 6, 1), date(2026, 9, 30), source=sd,
                           name='NA en double')

    def test_na_face_a_un_autre_contrat_declare_refuse(self):
        """Un NA ne s'oppose pas à SON contrat déclaré, mais bien à un autre."""
        sd_ancien = self._contract('declared', 'close', date(2025, 1, 1), date(2025, 12, 31))
        self._contract('declared', 'open', date(2026, 1, 1))
        with self.assertRaises(ValidationError):
            self._contract('not_declared', 'open_not_declared', date(2025, 1, 1), source=sd_ancien,
                           name='NA qui déborde sur le contrat suivant')

    def test_deux_contrats_declares_chevauchants_refuses(self):
        """Le contrôle d'origine entre contrats déclarés est inchangé."""
        self._contract('declared', 'open', date(2026, 1, 1))
        with self.assertRaises(ValidationError):
            self._contract('declared', 'open', date(2026, 6, 1), name='Second contrat déclaré')

    def test_renouvellement_sans_chevauchement_accepte(self):
        """Ancien couple SD/NA clos, nouveau couple en cours ensuite : accepté."""
        sd1 = self._contract('declared', 'close', date(2025, 1, 1), date(2025, 12, 31))
        self._contract('not_declared', 'close', date(2025, 1, 1), date(2025, 12, 31), source=sd1)
        sd2 = self._contract('declared', 'open', date(2026, 1, 1))
        na2 = self._contract('not_declared', 'open_not_declared', date(2026, 1, 1), source=sd2)
        self.assertEqual(na2.contract_id, sd2)


@tagged('post_install', '-at_install')
class TestContrainteNAParcours(TransactionCase):
    """ Les VRAIS parcours métier : passage en cours (création du miroir par
    copy()), clôture et modification de date (propagées au NA en SQL brut par
    hr.contract.write), renouvellement.

    hr.contract.write fait un cr.commit() après chaque propagation au NA : il
    est neutralisé ici, sans quoi le test validerait ses données en base.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.structure_type = cls.env['hr.payroll.structure.type'].search([], limit=1)
        if not cls.structure_type:
            raise unittest.SkipTest("Aucun type de structure de paie en base.")
        cls.employee = cls.env['hr.employee'].with_company(cls.company).with_context(
            **SILENCIEUX).create({'name': 'Salarié Test Parcours NA', 'company_id': cls.company.id})

    def setUp(self):
        super().setUp()
        self.patch(self.env.cr, 'commit', lambda *args, **kwargs: None)

    def _declared(self, start, end=False):
        """Contrat déclaré créé en brouillon, comme depuis l'interface."""
        return self.env['hr.contract'].with_company(self.company).with_context(**SILENCIEUX).create({
            'name': 'Parcours NA %s' % start,
            'employee_id': self.employee.id,
            'company_id': self.company.id,
            'date_start': start,
            'date_end': end,
            'wage': 300000.0,
            'family_allowance': 0.0,
            'state': 'draft',
            'contract_category': 'declared',
            'structure_type_id': self.structure_type.id,
        })

    def _mirror(self, declared):
        self.env.invalidate_all()                 # le NA est mis à jour en SQL brut
        return self.env['hr.contract'].search([('contract_id', '=', declared.id),
                                               ('contract_category', '=', 'not_declared')])

    def _open(self, declared):
        declared.with_context(**SILENCIEUX).write({'state': 'open'})
        return self._mirror(declared)

    def test_a_passage_en_cours_cree_le_miroir(self):
        sd = self._declared(date(2026, 1, 1))
        na = self._open(sd)
        self.assertEqual(len(na), 1, "un et un seul NA miroir")
        self.assertEqual(na.state, 'open_not_declared')
        self.assertEqual(na.contract_id, sd)
        self.assertEqual(na.date_start, sd.date_start)

    def test_b_cloture_du_contrat_declare_clot_le_na(self):
        sd = self._declared(date(2026, 1, 1))
        self._open(sd)
        sd.with_context(**SILENCIEUX).write({'date_end': date(2026, 9, 30)})
        sd.with_context(**SILENCIEUX).write({'state': 'close'})
        na = self._mirror(sd)
        self.assertEqual((sd.state, na.state), ('close', 'close'))
        self.assertEqual(na.date_end, date(2026, 9, 30))

    def test_c_renouvellement(self):
        ancien = self._declared(date(2025, 1, 1))
        self._open(ancien)
        ancien.with_context(**SILENCIEUX).write({'date_end': date(2025, 12, 31)})
        ancien.with_context(**SILENCIEUX).write({'state': 'close'})
        self.assertEqual(self._mirror(ancien).state, 'close')

        nouveau = self._declared(date(2026, 1, 1))
        na = self._open(nouveau)
        self.assertEqual(nouveau.state, 'open')
        self.assertEqual((len(na), na.state, na.contract_id), (1, 'open_not_declared', nouveau))

    def test_d_date_de_fin_propagee_au_na(self):
        sd = self._declared(date(2026, 1, 1))
        self._open(sd)
        sd.with_context(**SILENCIEUX).write({'date_end': date(2026, 12, 31)})
        na = self._mirror(sd)
        self.assertEqual(na.date_end, date(2026, 12, 31))
        self.assertEqual(na.state, 'open_not_declared')
