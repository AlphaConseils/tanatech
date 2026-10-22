# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Préavis non effectué sur le solde de tout compte (migration 18.0.1.2.30).

Deux cas client de septembre 2026 :
- RANOMENJANAHARY : solde 27,5 j, préavis 15 j -> 12,5 j payés, rien retenu ;
- SONORA : solde 13,05 j, préavis 30 j -> 0 j payé, 16,95 j retenus sur
  309 200 + 350 000 = 659 200, soit 16,95 x 659 200 / 30 = 372 448 : le net
  à payer NA tombe à 0, le reste est retenu sur le STC déclaré.

Les méthodes du module sont testées partout. Les VRAIES règles de la base
(CPALLOC, RETPREAV) ne le sont que si la migration les a réécrites : sinon ces
tests se sautent en le disant. Comme pour TestPattyAout, aucune société ni
structure n'est créée : elles sont retrouvées par nom normalisé.
"""

import unittest

from datetime import date

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.tanatech_hr_payroll.models.hr_payslip import PREAVIS_RETENUE

from .test_patty_aout import SILENCIEUX, _norm

SORTIE = date(2026, 9, 30)
SEPT_DEBUT = date(2026, 9, 1)
MARQUEUR = 'PATTY_PREAVIS'


@tagged('post_install', '-at_install')
class TestRetenuePreavis(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        companies = cls.env['res.company'].search([])
        cls.company = companies.filtered(lambda c: _norm(c.name) == _norm('TANATECH'))
        structures = cls.env['hr.payroll.structure'].with_context(active_test=False).search([])
        cls.struct_sd = structures.filtered(lambda s: _norm(s.name) == _norm('Solde Tout Compte'))
        cls.struct_na = structures.filtered(lambda s: _norm(s.name) == _norm('Solde Tout Compte - NA'))
        if len(cls.company) != 1 or len(cls.struct_sd) != 1 or len(cls.struct_na) != 1:
            raise unittest.SkipTest(
                "Société TANATECH ou structures « Solde Tout Compte » (SD et NA) "
                "introuvables par nom : ces tests ne les créent pas.")
        if cls.struct_sd.na_structure_id != cls.struct_na:
            raise unittest.SkipTest(
                "La structure %r ne pointe pas vers %r (na_structure_id) : le "
                "bulletin NA jumeau ne serait pas créé." % (cls.struct_sd.name, cls.struct_na.name))

        entry_type = cls.env['hr.work.entry.type'].search([('code', '=', 'LEAVE120')], limit=1)
        if not entry_type:
            raise unittest.SkipTest("Aucun type d'entrée de travail LEAVE120 en base.")
        cls.cp_type = cls.env['hr.leave.type'].with_company(cls.company).with_context(**SILENCIEUX).create({
            'name': 'Congé payé (test préavis)',
            'requires_allocation': 'yes',
            'allocation_validation_type': 'no_validation',
            'leave_validation_type': 'no_validation',
            'request_unit': 'half_day',
            'work_entry_type_id': entry_type.id,
            'company_id': cls.company.id,
        })
        cls.calendar = cls.env['resource.calendar'].with_company(cls.company).with_context(**SILENCIEUX).create({
            'name': 'Horaire test préavis',
            'company_id': cls.company.id,
            'tz': 'Indian/Antananarivo',
            'attendance_ids': [Command.clear()] + [
                Command.create({'name': 'Jour', 'dayofweek': day, 'hour_from': 8.0,
                                'hour_to': 16.0, 'day_period': 'morning'})
                for day in '012345'],
        })
        cls.input_preavis = cls._input_type('PREAVNE', 'Jours de préavis non effectués')
        cls.input_lic02 = cls._input_type('LIC02', 'Indemnité compensatrice de congé non prise')
        cls.input_preav01 = cls._input_type('PREAV01', 'Indemnité de préavis')

    @classmethod
    def _input_type(cls, code, name):
        """Le type de saisie de ce code, celui de la base de préférence."""
        found = cls.env['hr.payslip.input.type'].search([('code', '=', code)], limit=1)
        return found or cls.env['hr.payslip.input.type'].create({
            'name': name, 'code': code,
            'struct_ids': [Command.set((cls.struct_sd | cls.struct_na).ids)]})

    # ------------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------------

    def _sortant(self, nom, solde, salaire_sd, salaire_na, preavis=0.0):
        """Un salarié sorti le 30/09 avec ses deux contrats clos, son solde de
        congés, et ses bulletins STC (le NA est créé par le module à la création
        du déclaré). Renvoie (bulletin déclaré, bulletin NA)."""
        employee = self.env['hr.employee'].with_company(self.company).with_context(**SILENCIEUX).create({
            'name': nom, 'company_id': self.company.id,
            'resource_calendar_id': self.calendar.id, 'tz': 'Indian/Antananarivo'})
        contracts = {}
        for category, wage in (('declared', salaire_sd), ('not_declared', salaire_na)):
            contracts[category] = self.env['hr.contract'].with_company(self.company).with_context(
                **SILENCIEUX).create({
                    'name': '%s (%s)' % (nom, category),
                    'employee_id': employee.id,
                    'company_id': self.company.id,
                    'date_start': date(2024, 1, 1),
                    'date_end': SORTIE,
                    'wage': wage,
                    'family_allowance': 0.0,
                    'state': 'close',
                    'contract_category': category,
                    'structure_type_id': (self.struct_sd if category == 'declared' else self.struct_na).type_id.id,
                    'resource_calendar_id': self.calendar.id,
                    'contract_id': contracts['declared'].id if category == 'not_declared' else False,
                })
        if solde:
            allocation = self.env['hr.leave.allocation'].with_company(self.company).with_context(
                **SILENCIEUX).create({
                    'name': 'Solde test préavis',
                    'employee_id': employee.id,
                    'holiday_status_id': self.cp_type.id,
                    'number_of_days': solde,
                    'allocation_type': 'regular',
                    'date_from': date(2024, 1, 1),
                })
            if allocation.state != 'validate':
                allocation.action_validate()
            self.assertEqual(allocation.state, 'validate')

        sd = self.env['hr.payslip'].with_company(self.company).with_context(**SILENCIEUX).create({
            'name': 'STC test préavis %s' % nom,
            'employee_id': employee.id,
            'contract_id': contracts['declared'].id,
            'struct_id': self.struct_sd.id,
            'company_id': self.company.id,
            'date_from': SEPT_DEBUT,
            'date_to': SORTIE,
        })
        na = self.env['hr.payslip'].search([
            ('employee_id', '=', employee.id), ('struct_id', '=', self.struct_na.id)])
        self.assertEqual(len(na), 1, "le bulletin STC NA jumeau doit être créé avec le déclaré")
        if preavis:
            self._saisie(sd, self.input_preavis, preavis)
        return sd, na

    def _saisie(self, payslip, input_type, amount):
        self.env['hr.payslip.input'].create({
            'payslip_id': payslip.id, 'input_type_id': input_type.id, 'amount': amount})
        payslip.invalidate_recordset(['input_line_ids'])

    def _regle_migree(self, structure, code):
        rule = self.env['hr.salary.rule'].with_context(active_test=False).search([
            ('struct_id', '=', structure.id), ('code', '=', code)])
        if len(rule) != 1 or MARQUEUR not in (rule.amount_python_compute or ''):
            self.skipTest(
                "La règle %s de %r n'est pas (ou pas une seule fois) passée par "
                "la migration 18.0.1.2.30 : voir les logs « PATTY_PREAVIS : »."
                % (code, structure.name))
        return rule

    @staticmethod
    def _ligne(payslip, code):
        return payslip.line_ids.filtered(lambda l: l.code == code)

    # ------------------------------------------------------------------
    # Méthodes du module
    # ------------------------------------------------------------------

    def test_ranomenjanahary_preavis_couvert_par_le_solde(self):
        """Solde 27,5, préavis 15 : 12,5 j payés, rien retenu, sur SD et NA."""
        sd, na = self._sortant('Test Ranomenjanahary', 27.5, 309200.0, 150000.0, preavis=15)
        attendu = {'solde': 27.5, 'preavis': 15.0, 'conges_payes': 12.5, 'reste': 0.0}
        self.assertEqual(sd._tanatech_preavis_split(), attendu)
        # Le bulletin NA lit la saisie sur son jumeau déclaré.
        self.assertEqual(na._tanatech_preavis_split(), attendu)

    def test_sonora_preavis_au_dela_du_solde(self):
        """Solde 13,05, préavis 30 : 0 j payé, 16,95 j retenus sur 659 200 / 30."""
        sd, na = self._sortant('Test Sonora', 13.05, 309200.0, 350000.0, preavis=30)
        split = na._tanatech_preavis_split()
        self.assertEqual(split, {'solde': 13.05, 'preavis': 30.0, 'conges_payes': 0.0, 'reste': 16.95})
        base = na._tanatech_period_wages()
        self.assertEqual(base, 659200.0, "base = salaire déclaré + salaire NA de la période")
        self.assertAlmostEqual(split['reste'] * base / 30.0, 372448.0, places=0)

    def test_sans_preavis_le_solde_est_paye_en_entier(self):
        """Aucune saisie : rien ne change, tout le solde est payé."""
        sd, na = self._sortant('Test Sans Preavis', 13.05, 309200.0, 350000.0)
        self.assertEqual(na._tanatech_preavis_split(),
                         {'solde': 13.05, 'preavis': 0.0, 'conges_payes': 13.05, 'reste': 0.0})

    def test_jumeau_annule_ignore(self):
        """Un bulletin déclaré annulé (lot en double) ne porte plus la saisie."""
        sd, na = self._sortant('Test Jumeau Annule', 13.05, 309200.0, 350000.0, preavis=30)
        sd.write({'state': 'cancel'})
        self.assertEqual(na._tanatech_preavis_days(), 0.0)

    def test_double_compte_preav01_refuse(self):
        """Préavis non effectué + PREAV01 (préavis payé) : calcul refusé."""
        sd, na = self._sortant('Test Double Preav01', 13.05, 309200.0, 350000.0, preavis=30)
        self._saisie(sd, self.input_preav01, 30)
        with self.assertRaises(UserError):
            sd.compute_sheet()

    def test_double_compte_lic02_refuse_meme_sur_le_na(self):
        """Préavis non effectué sur le SD + LIC02 sur le NA : calcul du NA refusé."""
        sd, na = self._sortant('Test Double Lic02', 27.5, 309200.0, 150000.0, preavis=15)
        self._saisie(na, self.input_lic02, 5)
        with self.assertRaises(UserError):
            na.compute_sheet()

    # ------------------------------------------------------------------
    # Vraies règles de la base, après migration
    # ------------------------------------------------------------------

    def test_regles_ranomenjanahary(self):
        """Bulletins calculés : CPALLOC à 12,5 j sur SD et NA, aucune retenue."""
        self._regle_migree(self.struct_sd, 'CPALLOC')
        self._regle_migree(self.struct_na, 'RETPREAV')
        sd, na = self._sortant('Test Regles Ranomenjanahary', 27.5, 309200.0, 150000.0, preavis=15)
        (sd | na).compute_sheet()
        for slip, wage in ((sd, 309200.0), (na, 150000.0)):
            line = self._ligne(slip, 'CPALLOC')
            self.assertEqual(len(line), 1)
            self.assertAlmostEqual(line.quantity, 12.5)
            # Total arrondi à la centaine par la devise (MGA, rounding = 100).
            self.assertAlmostEqual(line.total, 12.5 * wage / 24.0, delta=50)
        self.assertFalse(self._ligne(na, 'RETPREAV'))

    def _nets(self, slip):
        return (self._ligne(slip, 'SALNETAP').total, self._ligne(slip, PREAVIS_RETENUE).total)

    def test_regles_sonora(self):
        """Bulletins calculés : aucun CPALLOC ; la retenue de 372 448 met le net
        à payer NA à 0 et le reste est retenu sur le STC déclaré."""
        self._regle_migree(self.struct_sd, 'CPALLOC')
        self._regle_migree(self.struct_sd, PREAVIS_RETENUE)
        self._regle_migree(self.struct_na, PREAVIS_RETENUE)
        sd, na = self._sortant('Test Regles Sonora', 13.05, 309200.0, 350000.0, preavis=30)
        # Calculer le seul STC déclaré suffit : son jumeau NA est recalculé avant lui.
        sd.compute_sheet()
        self.assertFalse(self._ligne(sd, 'CPALLOC'))
        self.assertFalse(self._ligne(na, 'CPALLOC'))

        net_na, retenue_na = self._nets(na)
        net_sd, retenue_sd = self._nets(sd)
        self.assertEqual(net_na, 0.0, "le net à payer NA est entièrement absorbé")
        self.assertLess(retenue_na, 0.0)
        self.assertLess(retenue_sd, 0.0, "le reste déborde sur le STC déclaré")
        # 372 448 arrondi à la centaine par la devise : chaque ligne est stockée
        # à 100 Ar près (MGA, rounding = 100), le total retenu aussi.
        self.assertAlmostEqual(retenue_na + retenue_sd, -372448.0, delta=100)
        self.assertGreaterEqual(net_sd, 0.0)

        # Le STC NA porte la formule : la retenue totale de 16,95 j, et la part
        # imputée sur son net en taux.
        line_na = self._ligne(na, PREAVIS_RETENUE)
        self.assertIn('16,95 j', line_na.name)
        self.assertAlmostEqual(line_na.amount, -372448.0, delta=50)
        self.assertLess(line_na.rate, 100.0)
        # Le STC déclaré n'affiche qu'un montant : ni jours, ni taux, ni base.
        line_sd = self._ligne(sd, PREAVIS_RETENUE)
        self.assertEqual(line_sd.name, 'Retenue préavis non effectué')
        self.assertEqual(line_sd.quantity, 1.0)
        self.assertEqual(line_sd.rate, 100.0)
        self.assertAlmostEqual(line_sd.amount, retenue_sd, places=2)
        # Catégorie AJUST : le brut et le net ne bougent pas, seul le net à payer.
        self.assertEqual(line_sd.category_id.code, 'AJUST')
        self.assertEqual(line_na.category_id.code, 'AJUST')
        self.assertFalse(sd.message_ids.filtered(lambda m: 'plafonnée' in (m.body or '')))

    def test_regles_plafonnement(self):
        """Retenue supérieure aux deux nets : les deux nets à payer restent
        >= 0, le non-retenu est signalé dans le chatter des deux bulletins."""
        self._regle_migree(self.struct_sd, PREAVIS_RETENUE)
        self._regle_migree(self.struct_na, PREAVIS_RETENUE)
        # Aucun solde, 90 jours de préavis : 90 x 400 000 / 30 = 1 200 000, bien
        # plus que les deux nets d'un mois.
        sd, na = self._sortant('Test Regles Plafond', 0.0, 300000.0, 100000.0, preavis=90)
        (na | sd).compute_sheet()
        net_na, retenue_na = self._nets(na)
        net_sd, retenue_sd = self._nets(sd)
        self.assertGreaterEqual(net_na, 0.0)
        self.assertGreaterEqual(net_sd, 0.0)
        retenu = -(retenue_na + retenue_sd)
        self.assertLess(retenu, 1200000.0)
        non_retenu = 1200000.0 - retenu
        for slip in (sd, na):
            messages = slip.message_ids.filtered(lambda m: 'plafonnée' in (m.body or ''))
            self.assertEqual(len(messages), 1, "un avertissement sur %s" % slip.name)
            self.assertIn('{:,.0f}'.format(non_retenu).replace(',', ' '), messages.body)

    # ------------------------------------------------------------------
    # Migration, fonction pure
    # ------------------------------------------------------------------

    def test_migration_cpalloc_corps_de_production(self):
        """Les corps CPALLOC de production sont réécrits une fois, et compilent."""
        migration = self._load_migration()
        condition = (
            "cp_days = 0.0\n"
            "for a in payslip.env['hr.leave.allocation'].search([('employee_id', '=', employee.id), "
            "('state', '=', 'validate'), ('holiday_status_id.work_entry_type_id.code', '=', 'LEAVE120')]):\n"
            "    cp_days += a.number_of_days - a.leaves_taken\n"
            "result = round(cp_days, 2) != 0")
        amount = (
            "cp_days = 0.0\n"
            "for a in payslip.env['hr.leave.allocation'].search([('employee_id', '=', employee.id), "
            "('state', '=', 'validate'), ('holiday_status_id.work_entry_type_id.code', '=', 'LEAVE120')]):\n"
            "    cp_days += a.number_of_days - a.leaves_taken\n"
            "result_qty = cp_days\n"
            "result = (contract.wage / 24.0)")
        for field, body in (('condition_python', condition), ('amount_python_compute', amount)):
            target, problem = migration._transform_cp(field, body)
            self.assertIsNone(problem)
            self.assertIn(MARQUEUR, target)
            self.assertIn('_tanatech_preavis_split(cp_days)', target)
            self.assertLess(target.index('_tanatech_preavis_split'),
                            target.index('result_qty' if field == 'amount_python_compute' else 'result = round'))
            self.assertNotIn('__', target)
            compile(target, '<test>', 'exec')
            # Idempotence.
            self.assertEqual(migration._transform_cp(field, target), (None, None))
        # Ancrage absent ou en double : refusé.
        for refuse in ("result = 0", amount + "\nresult_qty = cp_days"):
            target, problem = migration._transform_cp('amount_python_compute', refuse)
            self.assertIsNone(target)
            self.assertTrue(problem)

    def test_migration_retenue_compile_et_parametres_en_tete(self):
        migration = self._load_migration()
        for body in (migration._RET_CONDITION, migration._RET_BODY,
                     migration._RET_SD_CONDITION, migration._RET_SD_BODY):
            self.assertIsNone(migration._check(body))
        head = migration._RET_BODY.split('slip =')[0]
        self.assertIn('DIVISEUR = 30.0', head)
        self.assertIn('BASE_SD_PLUS_NA = True', head)
        # Une seule source pour la formule : le STC déclaré ne la porte pas.
        self.assertNotIn('DIVISEUR =', migration._RET_SD_BODY)

    @staticmethod
    def _load_migration():
        import importlib.util
        import os
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'migrations', '18.0.1.2.30', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('migration_18_0_1_2_30', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
