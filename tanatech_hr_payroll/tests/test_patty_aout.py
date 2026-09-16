# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Les quatre arbitrages de la paie d'août 2026 (migration 18.0.1.2.23).

Les tests portent sur les MÉTHODES du module, pas sur le corps des règles : le
corps des règles vit en base, il diffère d'un environnement à l'autre et n'est
pas reproductible en test. Ce que la migration écrit dans les règles est un
appel d'une ligne vers ces méthodes — c'est donc ici que le métier est vérifié.
"""

import importlib.util
import os

from datetime import date, datetime
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.tanatech_hr_payroll.models import hr_payslip as payslip_module


@tagged('post_install', '-at_install')
class TestPattyAout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Trois sociétés, comme en production : le jour férié du 15/08 est saisi
        # une fois par société, et la prime de mission est exclue sur l'une
        # d'elles.
        cls.company_tana = cls.env['res.company'].create({'name': 'TANATECH TEST'})
        cls.company_maso = cls.env['res.company'].create({'name': 'MASONTSIKA'})
        cls.company_study = cls.env['res.company'].create({'name': 'STUDYDAS TEST'})

        cls.leave_type = cls._leave_type('LEAVE120', 'Congé payé test')
        cls.matoff_type = cls._leave_type('MATOFF', 'Maternité test')

        cls.employee = cls._employee('Salarié Test', cls.company_tana)
        cls.contract = cls._contract(cls.employee, 300000.0)
        cls.payslip = cls._payslip(cls.employee, cls.contract,
                                   date(2026, 8, 1), date(2026, 8, 31))

        # Assomption : trois lignes, une par société, comme en base. Les deux
        # conventions de saisie rencontrées en production sont représentées —
        # journée locale (21:00 la veille -> 20:59) et journée UTC brute — pour
        # vérifier qu'aucune ne déborde sur le 14 ni sur le 16.
        cls._public_holiday(cls.company_tana,
                            datetime(2026, 8, 14, 21, 0), datetime(2026, 8, 15, 20, 59))
        cls._public_holiday(cls.company_maso,
                            datetime(2026, 8, 15, 0, 0), datetime(2026, 8, 15, 23, 59))
        cls._public_holiday(cls.company_study,
                            datetime(2026, 8, 14, 21, 0), datetime(2026, 8, 15, 20, 59))

    # ------------------------------------------------------------------
    # Fabriques
    # ------------------------------------------------------------------

    @classmethod
    def _leave_type(cls, entry_code, name):
        """ Un type de congé rattaché au type d'entrée voulu.

        hr.work.entry.type porte une contrainte d'unicité sur le code : on
        réutilise celui qui existe déjà en base plutôt que d'en créer un second.
        """
        WorkEntryType = cls.env['hr.work.entry.type']
        entry_type = WorkEntryType.search([('code', '=', entry_code)], limit=1)
        if not entry_type:
            entry_type = WorkEntryType.create({
                'name': name,
                'code': entry_code,
                'is_leave': True,
            })
        return cls.env['hr.leave.type'].create({
            'name': name,
            'requires_allocation': 'no',
            'leave_validation_type': 'no_validation',
            'request_unit': 'half_day',
            'work_entry_type_id': entry_type.id,
            'company_id': False,
        })

    @classmethod
    def _employee(cls, name, company):
        employee = cls.env['hr.employee'].create({
            'name': name,
            'company_id': company.id,
        })
        # Madagascar : UTC+3. Le fuseau décide de quel jour local un jour férié
        # stocké en UTC recouvre.
        employee.tz = 'Indian/Antananarivo'
        return employee

    @classmethod
    def _contract(cls, employee, wage, category='declared', source=None,
                  mission_eligible=True):
        # Les contrats sont créés dans leur état final : hr.contract.write fait
        # un cr.commit() sur les changements d'état (miroir NA), ce qui casserait
        # le point de sauvegarde du test.
        return cls.env['hr.contract'].create({
            'name': '%s %s' % (employee.name, category),
            'employee_id': employee.id,
            'company_id': employee.company_id.id,
            'date_start': date(2020, 1, 1),
            'wage': wage,
            'family_allowance': 0.0,
            'state': 'open' if category == 'declared' else 'open_not_declared',
            'contract_category': category,
            'contract_id': source.id if source else False,
            'tanatech_mission_eligible': mission_eligible,
        })

    @classmethod
    def _payslip(cls, employee, contract, date_from, date_to):
        return cls.env['hr.payslip'].create({
            'name': 'Bulletin test %s' % employee.name,
            'employee_id': employee.id,
            'contract_id': contract.id,
            'company_id': employee.company_id.id,
            'date_from': date_from,
            'date_to': date_to,
        })

    @classmethod
    def _public_holiday(cls, company, start, stop):
        return cls.env['resource.calendar.leaves'].create({
            'name': 'Assomption %s' % company.name,
            'company_id': company.id,
            'resource_id': False,
            'calendar_id': False,
            'date_from': start,
            'date_to': stop,
        })

    def _leave(self, employee, leave_type, start, stop, half=False):
        values = {
            'name': 'Congé test',
            'employee_id': employee.id,
            'holiday_status_id': leave_type.id,
            'request_date_from': start,
            'request_date_to': stop,
        }
        if half:
            values.update({
                'request_unit_half': True,
                'request_date_from_period': 'am',
            })
        leave = self.env['hr.leave'].with_context(
            leave_skip_state_check=True,
            mail_notrack=True,
            no_calendar_sync=True,
        ).create(values)
        self.assertEqual(
            leave.state, 'validate',
            "le type de congé de test doit produire un congé validé "
            "(leave_validation_type = 'no_validation')")
        return leave

    # ------------------------------------------------------------------
    # A. Jours de congé payé
    # ------------------------------------------------------------------

    def test_a_jours_conges_cas_client(self):
        """Cas de référence : 13/08 au 26/08 + demi-journée le 31/08 = 11,5 jours.

        Le 15/08 est un SAMEDI et l'Assomption : il compte 0 au titre du férié,
        et non 1 au titre du samedi. Les 16/08 et 23/08 sont des dimanches. Le
        22/08 est un samedi ordinaire et compte 1.
        """
        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 13), date(2026, 8, 26))
        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 31), date(2026, 8, 31), half=True)

        self.assertEqual(
            self.payslip._tanatech_leave_days('LEAVE120'), 11.5)

    def test_a_ferie_dedoublonne_et_ne_deborde_pas(self):
        """Le 15/08 saisi trois fois ne retire qu'un jour, et n'atteint ni le 14
        ni le 16."""
        holidays = self.payslip._tanatech_public_holidays()
        self.assertEqual(holidays, {date(2026, 8, 15)})

    def test_a_dimanche_et_samedi(self):
        """Le samedi est payé, le dimanche ne l'est pas.

        Du vendredi 21/08 au lundi 24/08 : 21 (vendredi) 1, 22 (samedi) 1,
        23 (dimanche) 0, 24 (lundi) 1 = 3 jours pour 4 jours calendaires.
        """
        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 21), date(2026, 8, 24))
        self.assertEqual(self.payslip._tanatech_leave_days('LEAVE120'), 3.0)
        # Le décompte calendaire, lui, en compte bien 4 : les deux méthodes ne
        # doivent pas être confondues.
        self.assertEqual(
            self.payslip._tanatech_calendar_leave_days('LEAVE120'), 4.0)

    def test_a_conge_a_cheval_sur_deux_mois(self):
        """Un congé du 28/08 au 03/09 ne pèse sur le bulletin d'août que pour
        ses jours d'août : 28 (vendredi), 29 (samedi), 30 (dimanche, 0),
        31 (lundi) = 3 jours."""
        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 28), date(2026, 9, 3))
        self.assertEqual(self.payslip._tanatech_leave_days('LEAVE120'), 3.0)

        septembre = self._payslip(self.employee, self.contract,
                                  date(2026, 9, 1), date(2026, 9, 30))
        # 01/09 mardi, 02/09 mercredi, 03/09 jeudi.
        self.assertEqual(septembre._tanatech_leave_days('LEAVE120'), 3.0)

    def test_a_retenue_et_indemnite(self):
        """Les deux règles de paie régulière consomment le même décompte : la
        retenue au taux ordinaire (/30) et l'indemnité au taux congé (/24)."""
        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 13), date(2026, 8, 26))
        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 31), date(2026, 8, 31), half=True)
        cp_days = self.payslip._tanatech_leave_days('LEAVE120')

        wage = self.contract.wage
        self.assertAlmostEqual(-(wage / 30.0) * cp_days, -115000.0, places=2)
        self.assertAlmostEqual((wage / 24.0) * cp_days, 143750.0, places=2)

    # ------------------------------------------------------------------
    # B. Maternité
    # ------------------------------------------------------------------

    def test_b_maternite_proratisee(self):
        """Salaire 300 000, maternité du 01/08 au 11/08 : -55 000.

        Le décompte est CALENDAIRE : ni le dimanche 02/08 ni le dimanche 09/08
        ne sont retirés, contrairement aux congés payés.
        """
        self._leave(self.employee, self.matoff_type,
                    date(2026, 8, 1), date(2026, 8, 11))

        mat_days = self.payslip._tanatech_calendar_leave_days('MATOFF', 30)
        self.assertEqual(mat_days, 11.0)

        wage = self.contract.wage
        self.assertAlmostEqual(
            -((wage / 2 / 30) * mat_days), -55000.0, places=2)

    def test_b_plafond_trente_jours(self):
        """Un congé de maternité qui couvre tout le mois reste plafonné."""
        self._leave(self.employee, self.matoff_type,
                    date(2026, 7, 15), date(2026, 9, 15))
        # Août compte 31 jours calendaires, le plafond en retient 30.
        self.assertEqual(
            self.payslip._tanatech_calendar_leave_days('MATOFF', 30), 30.0)
        self.assertEqual(
            self.payslip._tanatech_calendar_leave_days('MATOFF'), 31.0)

    def test_b_sans_conge_aucune_retenue(self):
        self.assertEqual(
            self.payslip._tanatech_calendar_leave_days('MATOFF', 30), 0.0)

    # ------------------------------------------------------------------
    # C. Assiette d'arrondi
    # ------------------------------------------------------------------

    @staticmethod
    def _result_rules(**totals):
        """Un result_rules minimal, à la forme que le moteur de paie expose."""
        return {code: {'total': total, 'amount': total, 'quantity': 1.0}
                for code, total in totals.items()}

    def test_c_frais_bancaires_hors_assiette(self):
        """Net 300 000 + frais 3 000 : on arrondit 300 000, on verse 303 000."""
        result_rules = self._result_rules(FRAISBANC=3000.0)
        net, opcomp = 300000.0, 3000.0

        salarr = self.payslip._tanatech_rounding_adjustment(
            net + opcomp, result_rules)
        self.assertEqual(salarr, 0.0)
        self.assertEqual(round(net + opcomp + salarr), 303000)

    def test_c_arrondi_reel_hors_frais(self):
        """Un net qui n'est pas rond est bien arrondi, les frais restant intacts."""
        result_rules = self._result_rules(FRAISBANC=3000.0)
        net, opcomp = 279060.0, 3000.0

        salarr = self.payslip._tanatech_rounding_adjustment(
            net + opcomp, result_rules)
        # 279 060 -> 280 000, puis les frais s'ajoutent sans second arrondi.
        self.assertEqual(round(net + opcomp + salarr), 283000)

    def test_c_allocations_dans_l_assiette(self):
        """Consigne écrite : ALLOC RESTE dans l'assiette d'arrondi.

        Net 300 000 + frais 3 000 + allocations 14 000. L'assiette vaut 314 000,
        elle s'arrondit à 315 000, et le net à payer sort à 318 000.

        Le brief annonçait 317 000 pour ce cas, ce qui suppose ALLOC HORS
        assiette : les deux énoncés ne peuvent pas être vrais ensemble. C'est
        l'énoncé de la règle qui est implémenté ici ;
        test_c_arrondi_alloc_hors_assiette mesure l'autre option, qui s'obtient
        en ajoutant un mot à FRAIS_HORS_ARRONDI.
        """
        result_rules = self._result_rules(FRAISBANC=3000.0, ALLOC=14000.0)
        net, opcomp = 300000.0, 17000.0

        salarr = self.payslip._tanatech_rounding_adjustment(
            net + opcomp, result_rules)
        self.assertEqual(salarr, 1000.0)
        self.assertEqual(round(net + opcomp + salarr), 318000)

    def test_c_arrondi_alloc_hors_assiette(self):
        """L'autre option client, à un mot près : ALLOC hors assiette -> 317 000."""
        result_rules = self._result_rules(FRAISBANC=3000.0, ALLOC=14000.0)
        net, opcomp = 300000.0, 17000.0

        with patch.object(payslip_module, 'FRAIS_HORS_ARRONDI',
                          ("FRAISBANC", "ALLOC")):
            salarr = self.payslip._tanatech_rounding_adjustment(
                net + opcomp, result_rules)
        self.assertEqual(salarr, 0.0)
        self.assertEqual(round(net + opcomp + salarr), 317000)

    def test_c_regle_non_declenchee(self):
        """Sans compte bancaire, pas de ligne FRAISBANC : rien à sortir de
        l'assiette, et surtout aucune erreur.

        302 000 s'arrondit à 300 000 (le plus proche des deux multiples), donc
        un ajustement de -2 000.
        """
        salarr = self.payslip._tanatech_rounding_adjustment(
            302000.0, self._result_rules())
        self.assertEqual(salarr, -2000.0)
        # result_rules absent du localdict : même réponse, pas d'exception.
        self.assertEqual(
            self.payslip._tanatech_rounding_adjustment(302000.0, None), -2000.0)

    def test_c_result_rules_objet_browsable(self):
        """Le moteur de paie expose result_rules sous forme d'objet, pas de dict
        nu : la lecture doit fonctionner dans les deux cas."""

        class _Browsable:
            def __init__(self, values):
                self.dict = values

        result_rules = _Browsable(self._result_rules(FRAISBANC=3000.0))
        self.assertEqual(
            self.payslip._tanatech_rule_total(result_rules, 'FRAISBANC'), 3000.0)
        self.assertEqual(
            self.payslip._tanatech_rule_total(result_rules, 'ALLOC'), 0.0)

    # ------------------------------------------------------------------
    # D. Prime de mission
    # ------------------------------------------------------------------

    def test_d_eligible_par_defaut(self):
        self.assertTrue(self.contract.tanatech_mission_eligible)
        self.assertTrue(self.payslip._tanatech_mission_eligible())

    def test_d_contrat_na_suit_le_contrat_declare(self):
        """Décocher le contrat DÉCLARÉ suffit : le bulletin NA ne verse plus.

        Les écritures sur le contrat déclaré ne sont pas propagées au contrat NA
        (tanatech_hr_contract ne propage qu'une liste fermée de champs). Sans
        cette règle, le client devrait décocher deux fois par salarié.
        """
        na_contract = self._contract(
            self.employee, 300000.0, category='not_declared',
            source=self.contract, mission_eligible=True)
        na_payslip = self._payslip(self.employee, na_contract,
                                   date(2026, 8, 1), date(2026, 8, 31))
        self.assertTrue(na_payslip._tanatech_mission_eligible())

        self.contract.tanatech_mission_eligible = False
        self.assertTrue(na_contract.tanatech_mission_eligible)
        self.assertFalse(na_payslip._tanatech_mission_eligible())

    def test_d_contrat_du_bulletin_decoche(self):
        na_contract = self._contract(
            self.employee, 300000.0, category='not_declared',
            source=self.contract, mission_eligible=False)
        na_payslip = self._payslip(self.employee, na_contract,
                                   date(2026, 8, 1), date(2026, 8, 31))
        self.assertFalse(na_payslip._tanatech_mission_eligible())

    def test_d_salarie_masontsika_prime_nulle(self):
        """Un salarié MASONTSIKA en mission ne touche aucune prime."""
        employee = self._employee('Salarié Masontsika', self.company_maso)
        declared = self._contract(employee, 250000.0, mission_eligible=False)
        na_contract = self._contract(
            employee, 250000.0, category='not_declared', source=declared,
            mission_eligible=False)
        na_payslip = self._payslip(employee, na_contract,
                                   date(2026, 8, 1), date(2026, 8, 31))

        self.assertFalse(na_payslip._tanatech_mission_eligible())
        # Ce que la règle MISS en fait : la condition est fausse, aucune ligne
        # n'est produite, donc zéro.
        bareme = 120000.0
        prime = bareme if na_payslip._tanatech_mission_eligible() else 0.0
        self.assertEqual(prime, 0.0)

    def test_d_initialisation_du_parc(self):
        """La migration pose False sur MASONTSIKA, True ailleurs, UNE seule fois.

        Le rejeu ne doit pas repasser derrière les décochages manuels du client
        (la liste des responsables TANATECH est cochée à la main).
        """
        migration = self._load_migration()
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(migration._MISS_INIT_PARAM, False)

        maso_employee = self._employee('Init Masontsika', self.company_maso)
        maso_contract = self._contract(maso_employee, 200000.0)
        tana_contract = self.contract

        self.assertTrue(migration._init_mission_eligible(self.env))
        self.assertFalse(maso_contract.tanatech_mission_eligible)
        self.assertTrue(tana_contract.tanatech_mission_eligible)

        # Décochage manuel, puis rejeu : la valeur du client survit.
        tana_contract.tanatech_mission_eligible = False
        self.assertTrue(migration._init_mission_eligible(self.env))
        self.assertFalse(tana_contract.tanatech_mission_eligible)

    # ------------------------------------------------------------------
    # Chargement du script de migration
    # ------------------------------------------------------------------

    @staticmethod
    def _load_migration():
        """Le post-migrate de 18.0.1.2.23, chargé par chemin.

        Le répertoire porte des points et le fichier un tiret : il n'est pas
        importable comme un module ordinaire.
        """
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'migrations', '18.0.1.2.23', 'post-migrate.py')
        spec = importlib.util.spec_from_file_location('patty_aout_migration', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_migration_corps_cibles_compilent(self):
        """Les corps que la migration écrit dans les règles sont du Python
        valide, et appellent bien les méthodes du module."""
        migration = self._load_migration()

        bodies = [
            (migration._CP_BODY % repr('LEAVE120'))
            + "\nresult = -(contract.wage / 30.0) * cp_days",
            migration._CP_CONDITION % repr('LEAVE120'),
            (migration._MATOFF_BODY % (repr('MATOFF'), 30))
            + "\nresult = -((contract.wage / 2 / 30) * mat_days)",
            migration._MATOFF_CONDITION % (repr('MATOFF'), 30),
            'to_pay = (categories.get("NET") or 0)\n' + migration._SALARR_RESULT,
            migration._MISS_CONDITION,
        ]
        for body in bodies:
            compile(body, '<test>', 'exec')
            # safe_eval refuse tout nom contenant un double souligné : les corps
            # produits ne doivent en porter aucun.
            self.assertNotIn('__', body)
