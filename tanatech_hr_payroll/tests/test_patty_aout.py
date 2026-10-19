# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""Les quatre arbitrages de la paie d'août 2026 (migration 18.0.1.2.23).

Les tests portent sur les MÉTHODES du module, pas sur le corps des règles : le
corps des règles vit en base, il diffère d'un environnement à l'autre et n'est
pas reproductible en test. Ce que la migration écrit dans les règles est un
appel d'une ligne vers ces méthodes, c'est donc ici que le métier est vérifié.

CE QUE CES TESTS NE CRÉENT PAS
------------------------------
Aucune société, aucune structure de paie. La création d'une res.company sur une
base réelle traverse les surcharges create de documents_hr_payroll, industry_fsm,
hr_payroll, timesheet_grid, l10n_fr_pos_cert, account_reports et compagnie, et
échoue : le setUpClass mourait avant le premier test. Les sociétés et les
structures sont donc RETROUVÉES par nom normalisé, jamais créées ni cherchées par
id, et la classe est sautée proprement si la base ne les porte pas.

Les jours fériés ne sont pas créés non plus. Le décompte des congés dépend de
ceux qui sont RÉELLEMENT en base ; les tests lisent donc la configuration de la
base et se sautent eux-mêmes, avec un message explicite, si elle n'est pas celle
qu'ils supposent. Un test qui passerait sur des fériés fabriqués ne dirait rien
de la paie du client.

Tout le reste (salariés, contrats, congés, bulletins) est créé dans la société du
contrat, en with_company et sans traçabilité, et disparaît au rollback.
"""

import importlib.util
import os
import re
import unicodedata
import unittest

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval

from odoo.addons.tanatech_hr_payroll.models import hr_payslip as payslip_module

# Contexte de création : aucune notification, aucun suivi, aucun message.
# Sur une base réelle, les surcharges de mail.thread transforment la moindre
# création en cascade d'écritures sans rapport avec ce qu'on teste.
SILENCIEUX = {
    'tracking_disable': True,
    'mail_create_nolog': True,
    'mail_notrack': True,
    'no_reset_password': True,
}

# Période du cas client.
AOUT_DEBUT = date(2026, 8, 1)
AOUT_FIN = date(2026, 8, 31)
ASSOMPTION = date(2026, 8, 15)


def _norm(label):
    """Clé de comparaison sans casse, sans accent, sans ponctuation.

    « Paie Régulière NA », « Paie régulière NA » et « PAIE REGULIERE NA »
    désignent la même structure : les libellés ne sont pas saisis deux fois de la
    même façon d'un environnement à l'autre.
    """
    text = unicodedata.normalize("NFKD", label or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-zA-Z]+", " ", text).strip().lower()


@tagged('post_install', '-at_install')
class TestPattyAout(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.company_tana = cls._find_company('TANATECH')
        cls.company_maso = cls._find_company('MASONTSIKA')

        cls.struct_sd = cls._find_structure('Paie Régulière')
        cls.struct_na = cls._find_structure('Paie régulière NA')
        # Les structures de solde de tout compte ne servent qu'au volet D ; leur
        # absence ne doit pas faire sauter toute la classe.
        cls.struct_stc_sd = cls._find_structure('Solde Tout Compte', required=False)
        cls.struct_stc_na = cls._find_structure('Solde Tout Compte - NA', required=False)

        cls.leave_type = cls._leave_type('LEAVE120', 'Congé payé (test Patty)')
        cls.matoff_type = cls._leave_type('MATOFF', 'Maternité (test Patty)')

        cls.employee = cls._employee('Salarié Test Patty', cls.company_tana)
        cls.contract = cls._contract(cls.employee, 300000.0, cls.struct_sd)
        cls.payslip = cls._payslip(cls.employee, cls.contract, cls.struct_sd,
                                   AOUT_DEBUT, AOUT_FIN)

    # ------------------------------------------------------------------
    # Résolution des données existantes
    # ------------------------------------------------------------------

    @classmethod
    def _find_company(cls, name):
        """La société portant ce nom, jamais créée. Saute la classe si absente."""
        companies = cls.env['res.company'].search([])
        found = companies.filtered(lambda c: _norm(c.name) == _norm(name))
        if len(found) != 1:
            raise unittest.SkipTest(
                "La base ne porte pas exactement une société nommée %r "
                "(%s trouvée(s)) : ces tests s'appuient sur les sociétés "
                "réelles et ne peuvent pas en créer." % (name, len(found)))
        return found

    @classmethod
    def _find_structure(cls, name, required=True):
        """La structure de paie portant ce nom, par nom NORMALISÉ, jamais par id.

        Les ids diffèrent entre stage_2 et production : les chercher par id
        donnerait un test qui passe sur une base et ment sur l'autre.
        """
        structures = cls.env['hr.payroll.structure'].with_context(
            active_test=False).search([])
        found = structures.filtered(lambda s: _norm(s.name) == _norm(name))
        if len(found) != 1:
            if not required:
                return cls.env['hr.payroll.structure']
            raise unittest.SkipTest(
                "La base ne porte pas exactement une structure nommée %r "
                "(%s trouvée(s)) : ces tests s'appuient sur les structures "
                "réelles et ne peuvent pas en créer." % (name, len(found)))
        return found

    # ------------------------------------------------------------------
    # Fabriques, toutes dans la société du contrat
    # ------------------------------------------------------------------

    @classmethod
    def _leave_type(cls, entry_code, name):
        """Un type de congé rattaché au type d'entrée voulu.

        hr.work.entry.type porte une contrainte d'unicité sur le code : on
        réutilise celui qui est déjà en base, on n'en crée jamais un second.
        """
        entry_type = cls.env['hr.work.entry.type'].search(
            [('code', '=', entry_code)], limit=1)
        if not entry_type:
            raise unittest.SkipTest(
                "Aucun type d'entrée de travail de code %r en base : le "
                "décompte des congés de ce code n'est pas vérifiable."
                % entry_code)
        return cls.env['hr.leave.type'].with_company(
            cls.company_tana).with_context(**SILENCIEUX).create({
                'name': name,
                'requires_allocation': 'no',
                'leave_validation_type': 'no_validation',
                'request_unit': 'half_day',
                'work_entry_type_id': entry_type.id,
                'company_id': cls.company_tana.id,
            })

    @classmethod
    def _employee(cls, name, company):
        employee = cls.env['hr.employee'].with_company(company).with_context(
            **SILENCIEUX).create({
                'name': name,
                'company_id': company.id,
                'resource_calendar_id': company.resource_calendar_id.id,
            })
        # Madagascar : UTC+3. Le fuseau décide de quel jour local un jour férié
        # stocké en UTC recouvre.
        employee.tz = 'Indian/Antananarivo'
        return employee

    @classmethod
    def _contract(cls, employee, wage, structure, category='declared',
                  source=None, mission_eligible=True, state=None,
                  date_start=None, date_end=False):
        # Les contrats sont créés dans leur état final : hr.contract.write fait
        # un cr.commit() sur les changements d'état (miroir NA), ce qui casserait
        # le point de sauvegarde du test.
        return cls.env['hr.contract'].with_company(
            employee.company_id).with_context(**SILENCIEUX).create({
                'name': '%s (%s)' % (employee.name, category),
                'employee_id': employee.id,
                'company_id': employee.company_id.id,
                'date_start': date_start or date(2020, 1, 1),
                'date_end': date_end,
                'wage': wage,
                'family_allowance': 0.0,
                'state': state or (
                    'open' if category == 'declared' else 'open_not_declared'),
                'contract_category': category,
                'structure_type_id': structure.type_id.id,
                'resource_calendar_id': employee.resource_calendar_id.id,
                'contract_id': source.id if source else False,
                'tanatech_mission_eligible': mission_eligible,
            })

    @classmethod
    def _payslip(cls, employee, contract, structure, date_from, date_to):
        return cls.env['hr.payslip'].with_company(
            employee.company_id).with_context(**SILENCIEUX).create({
                'name': 'Bulletin test Patty %s' % employee.name,
                'employee_id': employee.id,
                'contract_id': contract.id,
                'struct_id': structure.id,
                'company_id': employee.company_id.id,
                'date_from': date_from,
                'date_to': date_to,
            })

    def _leave(self, employee, leave_type, start, stop, half=False):
        values = {
            'name': 'Congé test Patty',
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
        leave = self.env['hr.leave'].with_company(
            employee.company_id).with_context(
                leave_skip_state_check=True, no_calendar_sync=True,
                **SILENCIEUX).create(values)
        self.assertEqual(
            leave.state, 'validate',
            "le type de congé de test doit produire un congé validé "
            "(leave_validation_type = 'no_validation')")
        return leave

    # ------------------------------------------------------------------
    # Garde : la configuration des jours fériés de la base
    # ------------------------------------------------------------------

    def _require_holidays(self, payslip, attendus, debut, fin):
        """Exiger que les jours fériés de la base, sur [debut, fin], soient
        exactement ``attendus``. Saute le test sinon, en le disant.

        Aucun jour férié n'est fabriqué : le décompte des congés du client repose
        sur ceux qui sont réellement saisis, et un test qui les inventerait ne
        dirait rien de sa paie.
        """
        reels = {jour for jour in payslip._tanatech_public_holidays()
                 if debut <= jour <= fin}
        if reels != set(attendus):
            self.skipTest(
                "Jours fériés en base sur %s..%s pour la société %s : %s. "
                "Ce test suppose %s : configuration différente, résultat non "
                "comparable." % (
                    debut, fin, payslip.employee_id.company_id.name,
                    sorted(reels) or 'aucun', sorted(attendus) or 'aucun'))

    # ------------------------------------------------------------------
    # A. Jours de congé payé
    # ------------------------------------------------------------------

    def test_a_jours_conges_cas_client(self):
        """Cas de référence : 13/08 au 26/08 + demi-journée le 31/08 = 11,5 jours.

        Le 15/08 est un SAMEDI et l'Assomption : il compte 0 au titre du férié,
        et non 1 au titre du samedi. Les 16/08 et 23/08 sont des dimanches. Le
        22/08 est un samedi ordinaire et compte 1.
        """
        self._require_holidays(self.payslip, [ASSOMPTION],
                               date(2026, 8, 13), date(2026, 8, 31))

        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 13), date(2026, 8, 26))
        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 31), date(2026, 8, 31), half=True)

        self.assertEqual(self.payslip._tanatech_leave_days('LEAVE120'), 11.5)

    def test_a_ferie_lu_en_base_et_sans_debordement(self):
        """L'Assomption, saisie une fois par société, ne retire qu'un jour et
        n'atteint ni la veille ni le lendemain.

        Le dédoublonnage entre les trois sociétés et la conversion du stockage
        UTC vers le jour local sont tous les deux exercés ici, sur la
        configuration réelle de la base.
        """
        lignes = self.env['resource.calendar.leaves'].search([
            ('resource_id', '=', False),
            ('date_from', '<=', '2026-08-16 00:00:00'),
            ('date_to', '>=', '2026-08-14 00:00:00'),
        ])
        if not lignes:
            self.skipTest(
                "Aucun jour férié global saisi autour du 15/08/2026 en base.")

        jours = self.payslip._tanatech_public_holidays()
        self.assertIn(ASSOMPTION, jours,
                      "l'Assomption doit être reconnue pour la société du salarié")
        self.assertNotIn(date(2026, 8, 14), jours,
                         "le férié ne doit pas déborder sur la veille")
        self.assertNotIn(date(2026, 8, 16), jours,
                         "le férié ne doit pas déborder sur le lendemain")
        # jours est un ensemble de dates : les lignes saisies par société ne
        # peuvent pas retirer le même jour plusieurs fois.
        self.assertEqual(
            len([j for j in jours if j == ASSOMPTION]), 1,
            "les %s lignes de férié autour du 15/08 ne doivent retirer qu'un "
            "jour" % len(lignes))

    def test_a_dimanche_et_samedi(self):
        """Le samedi est payé, le dimanche ne l'est pas.

        Du vendredi 21/08 au lundi 24/08 : 21 (vendredi) 1, 22 (samedi) 1,
        23 (dimanche) 0, 24 (lundi) 1 = 3 jours pour 4 jours calendaires.
        """
        self._require_holidays(self.payslip, [],
                               date(2026, 8, 21), date(2026, 8, 24))

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
        31 (lundi) = 3 jours.
        """
        septembre = self._payslip(self.employee, self.contract, self.struct_sd,
                                  date(2026, 9, 1), date(2026, 9, 30))
        self._require_holidays(self.payslip, [], date(2026, 8, 28), AOUT_FIN)
        self._require_holidays(septembre, [], date(2026, 9, 1), date(2026, 9, 3))

        self._leave(self.employee, self.leave_type,
                    date(2026, 8, 28), date(2026, 9, 3))

        self.assertEqual(self.payslip._tanatech_leave_days('LEAVE120'), 3.0)
        # 01/09 mardi, 02/09 mercredi, 03/09 jeudi.
        self.assertEqual(septembre._tanatech_leave_days('LEAVE120'), 3.0)

    def test_a_retenue_et_indemnite(self):
        """Les deux règles de paie régulière consomment le même décompte : la
        retenue au taux ordinaire (/30) et l'indemnité au taux congé (/24).
        """
        self._require_holidays(self.payslip, [ASSOMPTION],
                               date(2026, 8, 13), date(2026, 8, 31))

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
        ne sont retirés, contrairement aux congés payés. Aucune garde sur les
        jours fériés n'est nécessaire, ils ne sont pas déduits ici.
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

    def test_c_cas_reel_rakotoarinantenaina(self):
        """Le bulletin relevé en production le 16/09/2026.

        NET 394 100 + FRAISBANC 3 000 + ALLOC 24 000 = 421 100, qui sortait à
        420 000. Les frais hors assiette : 418 100 s'arrondit à 420 000, et les
        3 000 Ar reviennent intacts, soit 423 000.
        """
        result_rules = self._result_rules(FRAISBANC=3000.0, ALLOC=24000.0)
        net, opcomp = 394100.0, 27000.0

        salarr = self.payslip._tanatech_rounding_adjustment(
            net + opcomp, result_rules)
        self.assertEqual(salarr, 1900.0)
        self.assertEqual(round(net + opcomp + salarr), 423000)

    def test_c_allocations_dans_l_assiette(self):
        """Consigne écrite : ALLOC RESTE dans l'assiette d'arrondi.

        Net 300 000 + frais 3 000 + allocations 14 000. L'assiette vaut 314 000,
        elle s'arrondit à 315 000, et le net à payer sort à 318 000.

        Le brief annonçait 317 000 pour ce cas, ce qui suppose ALLOC HORS
        assiette : les deux énoncés ne peuvent pas être vrais ensemble. C'est
        l'énoncé de la règle qui est implémenté ici ;
        test_c_arrondi_alloc_hors_assiette mesure l'autre option.
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
        nu : la lecture doit fonctionner dans les deux cas.
        """

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
            self.employee, 300000.0, self.struct_na, category='not_declared',
            source=self.contract, mission_eligible=True)
        na_payslip = self._payslip(self.employee, na_contract, self.struct_na,
                                   AOUT_DEBUT, AOUT_FIN)
        self.assertTrue(na_payslip._tanatech_mission_eligible())

        self.contract.tanatech_mission_eligible = False
        self.assertTrue(na_contract.tanatech_mission_eligible)
        self.assertFalse(na_payslip._tanatech_mission_eligible())

    def test_d_contrat_du_bulletin_decoche(self):
        na_contract = self._contract(
            self.employee, 300000.0, self.struct_na, category='not_declared',
            source=self.contract, mission_eligible=False)
        na_payslip = self._payslip(self.employee, na_contract, self.struct_na,
                                   AOUT_DEBUT, AOUT_FIN)
        self.assertFalse(na_payslip._tanatech_mission_eligible())

    def test_d_salarie_masontsika_prime_nulle(self):
        """Un salarié MASONTSIKA en mission ne touche aucune prime.

        Tout est créé dans la société MASONTSIKA : contrat déclaré, contrat NA et
        bulletin. Rien n'est emprunté à la société du salarié TANATECH.
        """
        employee = self._employee('Salarié Masontsika Test Patty',
                                  self.company_maso)
        declared = self._contract(employee, 250000.0, self.struct_sd,
                                  mission_eligible=False)
        na_contract = self._contract(
            employee, 250000.0, self.struct_na, category='not_declared',
            source=declared, mission_eligible=False)
        na_payslip = self._payslip(employee, na_contract, self.struct_na,
                                   AOUT_DEBUT, AOUT_FIN)

        self.assertEqual(na_payslip.company_id, self.company_maso)
        self.assertFalse(na_payslip._tanatech_mission_eligible())
        # Ce que la règle MISS en fait : la condition est fausse, aucune ligne
        # n'est produite, donc zéro.
        bareme = 120000.0
        prime = bareme if na_payslip._tanatech_mission_eligible() else 0.0
        self.assertEqual(prime, 0.0)

    def test_d_defaut_suit_la_societe_du_contrat(self):
        """Un contrat créé APRÈS la migration naît non éligible chez MASONTSIKA.

        La valeur posée par la migration ne vaut que pour le parc existant :
        sans ce défaut, chaque embauche chez MASONTSIKA repartirait éligible.
        """
        Contract = self.env['hr.contract']

        maso = self._employee('Embauche Masontsika Test Patty', self.company_maso)
        contrat_maso = Contract.with_company(self.company_maso).with_context(
            default_company_id=self.company_maso.id, **SILENCIEUX).create({
                'name': 'Embauche Masontsika Test Patty',
                'employee_id': maso.id,
                'company_id': self.company_maso.id,
                'date_start': date(2026, 9, 1),
                'wage': 200000.0,
                'family_allowance': 0.0,
                'state': 'draft',
                'structure_type_id': self.struct_sd.type_id.id,
                'resource_calendar_id': maso.resource_calendar_id.id,
            })
        self.assertFalse(contrat_maso.tanatech_mission_eligible)

        tana = self._employee('Embauche Tanatech Test Patty', self.company_tana)
        contrat_tana = Contract.with_company(self.company_tana).with_context(
            default_company_id=self.company_tana.id, **SILENCIEUX).create({
                'name': 'Embauche Tanatech Test Patty',
                'employee_id': tana.id,
                'company_id': self.company_tana.id,
                'date_start': date(2026, 9, 1),
                'wage': 200000.0,
                'family_allowance': 0.0,
                'state': 'draft',
                'structure_type_id': self.struct_sd.type_id.id,
                'resource_calendar_id': tana.resource_calendar_id.id,
            })
        self.assertTrue(contrat_tana.tanatech_mission_eligible)

    def test_d_initialisation_du_parc(self):
        """La migration pose False sur MASONTSIKA, True ailleurs, UNE seule fois.

        Le rejeu ne doit pas repasser derrière les décochages manuels du client
        (la liste des responsables TANATECH est cochée à la main).
        """
        migration = self._load_migration()
        param = self.env['ir.config_parameter'].sudo()
        param.set_param(migration._MISS_INIT_PARAM, False)

        maso_employee = self._employee('Init Masontsika Test Patty',
                                       self.company_maso)
        maso_contract = self._contract(maso_employee, 200000.0, self.struct_sd)
        tana_contract = self.contract

        self.assertTrue(migration._init_mission_eligible(self.env))
        self.assertFalse(maso_contract.tanatech_mission_eligible)
        self.assertTrue(tana_contract.tanatech_mission_eligible)

        # Décochage manuel, puis rejeu : la valeur du client survit.
        tana_contract.tanatech_mission_eligible = False
        self.assertTrue(migration._init_mission_eligible(self.env))
        self.assertFalse(tana_contract.tanatech_mission_eligible)

    # ------------------------------------------------------------------
    # D. Écriture de la condition sur la règle MISS
    # ------------------------------------------------------------------

    def _miss_rule(self, condition_select='python', condition_python=False):
        """La règle MISS de la structure NA réelle, remise dans l'état voulu.

        La règle n'est pas créée : c'est celle de la base, celle que la migration
        modifiera. Le rollback du test lui rend sa condition d'origine.
        """
        if not self.struct_na:
            self.skipTest("Structure NA absente de la base.")
        rule = self.env['hr.salary.rule'].with_context(active_test=False).search([
            ('struct_id', '=', self.struct_na.id), ('code', '=', 'MISS'),
        ])
        if len(rule) != 1:
            self.skipTest(
                "La structure %r ne porte pas exactement une règle MISS "
                "(%s trouvée(s))." % (self.struct_na.name, len(rule)))
        rule.write({
            'condition_select': condition_select,
            'condition_python': condition_python,
        })
        return rule

    def test_d_condition_existante_conservee_et_durcie(self):
        """Une garde métier déjà en place est conservée, le critère s'ajoute.

        C'est le cas réel constaté au build de stage_2 : les deux règles MISS
        portaient déjà condition_select = 'python', et la première version du
        script refusait d'écrire, si bien qu'aucune éligibilité n'était posée.
        """
        migration = self._load_migration()
        garde = "result = bool(inputs.get('MISS'))"
        rule = self._miss_rule(condition_python=garde)

        self.assertTrue(migration._apply_miss_rule(self.env, rule, 'test'))

        condition = rule.condition_python
        self.assertIn(garde, condition,
                      "la garde d'origine doit être conservée telle quelle")
        self.assertIn('_tanatech_mission_eligible', condition)
        self.assertIn('result = result and', condition)
        self.assertTrue(condition.index(garde)
                        < condition.index('_tanatech_mission_eligible'),
                        "le critère doit venir APRÈS la garde d'origine")
        compile(condition, '<test>', 'exec')
        self.assertNotIn('__', condition)

        # Seconde exécution : le critère ne doit pas être ajouté une seconde fois.
        apres_premier_passage = condition
        self.assertFalse(migration._apply_miss_rule(self.env, rule, 'test'))
        self.assertEqual(rule.condition_python, apres_premier_passage)
        self.assertEqual(condition.count('_tanatech_mission_eligible'), 1)

    def test_d_condition_absente_pose_le_critere_seul(self):
        """condition_select = 'none' : le critère devient la condition."""
        migration = self._load_migration()
        rule = self._miss_rule(condition_select='none')

        self.assertTrue(migration._apply_miss_rule(self.env, rule, 'test'))
        self.assertEqual(rule.condition_select, 'python')
        self.assertIn('_tanatech_mission_eligible', rule.condition_python)
        self.assertNotIn('result = result and', rule.condition_python)

        self.assertFalse(migration._apply_miss_rule(self.env, rule, 'test'))

    def test_d_condition_par_intervalle_refusee(self):
        """condition_select = 'range' : on ne touche à rien."""
        migration = self._load_migration()
        rule = self._miss_rule(condition_select='range')
        avant = rule.condition_python

        self.assertFalse(migration._apply_miss_rule(self.env, rule, 'test'))
        self.assertEqual(rule.condition_select, 'range')
        self.assertEqual(rule.condition_python, avant)

    # ------------------------------------------------------------------
    # E. Heures travaillées un jour férié (migration 18.0.1.2.24)
    # ------------------------------------------------------------------

    def test_e_ferie_majoration_seule_50(self):
        """Un bulletin NA avec des heures WORKONPUBLICHOLIDAYS paie la seule
        majoration de 50 % : 0,5 x heures x (salaire déclaré + NA) / 173,33.

        Décision client du 21/09/2026. Les heures d'un jour férié sont déjà
        payées par le salaire de base, qui couvre tout le mois : ne reste due
        que la majoration.

        C'est la VRAIE règle de la base qui est évaluée, par le vrai safe_eval
        du moteur de paie, sur un vrai bulletin NA et les vrais contrats du
        salarié. Seules les heures sont fournies par un objet minimal : la
        règle n'en lit que number_of_hours, et les faire naître par des
        présences un jour férié ferait dépendre le test de tout le calendrier.
        """
        rules = self.env['hr.salary.rule'].with_context(active_test=False).search([
            ('struct_id', '=', self.struct_na.id),
            ('code', '=', 'WORKONPUBLICHOLIDAYS'),
        ])
        if len(rules) != 1:
            self.skipTest(
                "La structure %r ne porte pas exactement une règle "
                "WORKONPUBLICHOLIDAYS (%s trouvée(s))."
                % (self.struct_na.name, len(rules)))
        self.assertIn(
            'PATTY_FERIE', rules.amount_python_compute,
            "la migration 18.0.1.2.24 n'a pas posé la majoration seule sur "
            "cette règle : voir les logs « PATTY_FERIE : » du build")

        employee = self._employee('Salarié Férié Test Patty', self.company_tana)
        declared = self._contract(employee, 300000.0, self.struct_sd)
        na_contract = self._contract(
            employee, 100000.0, self.struct_na, category='not_declared',
            source=declared)
        na_payslip = self._payslip(employee, na_contract, self.struct_na,
                                   AOUT_DEBUT, AOUT_FIN)

        heures = 10.0
        localdict = {
            'employee': na_payslip.employee_id,
            'contract': na_payslip.contract_id,
            'payslip': na_payslip,
            'worked_days': {
                'WORKONPUBLICHOLIDAYS': SimpleNamespace(number_of_hours=heures),
            },
            'result': None,
            'result_qty': 1.0,
            'result_rate': 100,
            'result_name': False,
        }
        safe_eval(rules.amount_python_compute, localdict, mode='exec', nocopy=True)

        salaires = declared.wage + na_contract.wage
        attendu = 0.5 * heures * salaires / 173.33
        self.assertAlmostEqual(localdict['result'], attendu, places=2)
        # 0,5 x 10 x 400 000 / 173,33 : la moitié de ce que payait l'ancienne règle.
        self.assertAlmostEqual(localdict['result'], 11538.68, places=2)

    def test_e_migration_ferie_une_seule_ligne(self):
        """La migration 18.0.1.2.24 ne remplace que la ligne visée, une fois.

        Fonction pure, sans base : le code de production, la variante refusée,
        et le second passage qui ne doit rien réécrire.
        """
        migration = self._load_migration('18.0.1.2.24')
        prod = (
            "wages = sum(employee.contract_ids.filtered(lambda c: c.state in "
            "['open', 'open_not_declared']).mapped('wage'))\n"
            "res = 0\n"
            "if worked_days.get(\"WORKONPUBLICHOLIDAYS\"):\n"
            "    total_amount = (worked_days.get(\"WORKONPUBLICHOLIDAYS\")"
            ".number_of_hours* wages / 173.33)\n"
            "    res = total_amount\n"
            "result = res"
        )

        cible, motif = migration._transform(prod)
        self.assertIsNone(motif)
        self.assertIn(
            "    res = total_amount * 0.5  # PATTY_FERIE : majoration seule de "
            "50 %, décision client du 21/09/2026", cible)
        changees = [a for a, b in zip(prod.splitlines(), cible.splitlines())
                    if a != b]
        self.assertEqual(changees, ["    res = total_amount"],
                         "seule la ligne visée doit changer")
        self.assertNotIn('__', cible)
        compile(cible, '<test>', 'exec')

        # Idempotence : un corps déjà migré n'est pas réécrit.
        self.assertEqual(migration._transform(cible), (None, None))

        # Une variante n'est pas reconnue : rien n'est écrit, un motif est donné.
        variante, motif = migration._transform(
            prod.replace("    res = total_amount", "    res=total_amount"))
        self.assertIsNone(variante)
        self.assertTrue(motif)

    # ------------------------------------------------------------------
    # F. Frais de tenue de compte (migration 18.0.1.2.25)
    # ------------------------------------------------------------------

    def _bank_account(self, employee):
        """Un compte bancaire de test rattaché au salarié.

        La règle FRAISBANC ne lit bank_account_id qu'en booléen ; le numéro n'a
        pas d'importance, il est seulement choisi assez improbable pour ne pas
        heurter la contrainte d'unicité de la base.
        """
        partner = self.env['res.partner'].with_company(
            employee.company_id).with_context(**SILENCIEUX).create({
                'name': 'Banque test Patty %s' % employee.id,
                'company_id': employee.company_id.id,
            })
        account = self.env['res.partner.bank'].with_company(
            employee.company_id).with_context(**SILENCIEUX).create({
                'acc_number': 'TEST-PATTY-FRAIS-%s' % employee.id,
                'partner_id': partner.id,
                'company_id': employee.company_id.id,
            })
        employee.bank_account_id = account
        return account

    def _eval_rule(self, rule, employee, contract, **extra):
        """Évaluer le corps d'une règle comme le fait le moteur de paie."""
        localdict = {
            'employee': employee,
            'contract': contract,
            'result': None,
            'result_qty': 1.0,
            'result_rate': 100,
            'result_name': False,
        }
        localdict.update(extra)
        safe_eval(rule.amount_python_compute, localdict, mode='exec', nocopy=True)
        return localdict['result']

    def test_f_frais_bancaires_sans_seuil_de_salaire(self):
        """Salaire déclaré 533 700 avec compte bancaire : 3 000 Ar.

        Décision client du 23/09/2026 : les frais de tenue de compte
        s'appliquent à tout salarié payé par virement, sans condition de
        salaire. Avant, le seuil de 400 000 privait ce salarié des 3 000 Ar.

        C'est la VRAIE règle de la base qui est évaluée, par le vrai safe_eval
        du moteur de paie.
        """
        rules = self.env['hr.salary.rule'].with_context(active_test=False).search([
            ('struct_id', '=', self.struct_sd.id),
            ('code', '=', 'FRAISBANC'),
        ])
        if len(rules) != 1:
            self.skipTest(
                "La structure %r ne porte pas exactement une règle FRAISBANC "
                "(%s trouvée(s))." % (self.struct_sd.name, len(rules)))
        self.assertIn(
            'PATTY_FRAIS', rules.amount_python_compute,
            "la migration 18.0.1.2.25 n'a pas retiré le seuil de salaire sur "
            "cette règle : voir les logs « PATTY_FRAIS : » du build")

        employee = self._employee('Salarié Frais Test Patty', self.company_tana)
        contract = self._contract(employee, 533700.0, self.struct_sd)
        self._bank_account(employee)

        self.assertEqual(self._eval_rule(rules, employee, contract), 3000)

    def test_f_frais_bancaires_petit_salaire_inchange(self):
        """Sous l'ancien seuil, rien ne change : toujours 3 000 Ar."""
        rules = self.env['hr.salary.rule'].with_context(active_test=False).search([
            ('struct_id', '=', self.struct_sd.id),
            ('code', '=', 'FRAISBANC'),
        ])
        if len(rules) != 1:
            self.skipTest("Règle FRAISBANC introuvable sur %r."
                          % self.struct_sd.name)

        employee = self._employee('Salarié Petit Salaire Patty', self.company_tana)
        contract = self._contract(employee, 300000.0, self.struct_sd)
        self._bank_account(employee)

        self.assertEqual(self._eval_rule(rules, employee, contract), 3000)

    def test_f_frais_bancaires_sans_compte_rien(self):
        """Payé en espèces : aucun frais, la condition de compte reste.

        Seule la condition de SALAIRE a sauté. Un salarié sans compte bancaire
        ne doit toujours rien porter, quel que soit son salaire.
        """
        rules = self.env['hr.salary.rule'].with_context(active_test=False).search([
            ('struct_id', '=', self.struct_sd.id),
            ('code', '=', 'FRAISBANC'),
        ])
        if len(rules) != 1:
            self.skipTest("Règle FRAISBANC introuvable sur %r."
                          % self.struct_sd.name)

        employee = self._employee('Salarié Espèces Test Patty', self.company_tana)
        contract = self._contract(employee, 533700.0, self.struct_sd)
        self.assertFalse(employee.bank_account_id)

        self.assertEqual(self._eval_rule(rules, employee, contract), 0)

    def test_f_migration_frais_corps_attendu_seulement(self):
        """La migration 18.0.1.2.25 ne réécrit que le corps qu'elle attend.

        Fonction pure, sans base : le corps de production, l'idempotence, et
        les corps qui doivent être refusés.
        """
        migration = self._load_migration('18.0.1.2.25')
        prod = ("result = 3000 if ( employee.bank_account_id "
                "and contract.wage < 400000) else 0")

        cible, motif = migration._transform(prod)
        self.assertIsNone(motif)
        self.assertIn('PATTY_FRAIS', cible)
        self.assertIn('employee.bank_account_id', cible)
        self.assertNotIn('400000', cible)
        self.assertNotIn('contract.wage', cible)
        self.assertNotIn('__', cible)
        compile(cible, '<test>', 'exec')

        # Idempotence : un corps déjà migré n'est pas réécrit.
        self.assertEqual(migration._transform(cible), (None, None))

        # La mise en forme est indifférente, le sens ne l'est pas.
        sans_espace, motif = migration._transform(prod.replace('( employee', '(employee'))
        self.assertIsNone(motif)
        self.assertIsNotNone(sans_espace)
        for refuse in (
            prod.replace('400000', '500000'),
            prod.replace('3000', '5000'),
            "result = 0",
            "",
        ):
            corps, motif = migration._transform(refuse)
            self.assertIsNone(corps)
            self.assertTrue(motif)

    # ------------------------------------------------------------------
    # G. Base salariale de la période (migration 18.0.1.2.26)
    # ------------------------------------------------------------------

    @staticmethod
    def _ancienne_base(employee):
        """La formule que portaient les règles avant 1.2.26, pour comparaison."""
        return sum(employee.contract_ids.filtered(
            lambda c: c.state in ['open', 'open_not_declared']).mapped('wage'))

    def _salarie_deux_contrats(self, nom, declare=300000.0, na=100000.0,
                               state=None, date_end=False):
        """Un salarié, ses deux contrats et son bulletin NA d'août."""
        employee = self._employee(nom, self.company_tana)
        declared = self._contract(
            employee, declare, self.struct_sd,
            state='close' if state == 'close' else None, date_end=date_end)
        na_contract = self._contract(
            employee, na, self.struct_na, category='not_declared',
            source=declared,
            state='close' if state == 'close' else None, date_end=date_end)
        payslip = self._payslip(employee, na_contract, self.struct_na,
                                AOUT_DEBUT, AOUT_FIN)
        return employee, declared, na_contract, payslip

    def test_g_base_identique_quand_les_contrats_sont_en_cours(self):
        """Contrats en cours : la nouvelle base vaut exactement l'ancienne.

        C'est l'exigence de non régression : le correctif ne doit rien changer
        pour un salarié présent.
        """
        employee, declared, na_contract, payslip = self._salarie_deux_contrats(
            'Base En Cours Test Patty')

        self.assertEqual(payslip._tanatech_period_wages(), 400000.0)
        self.assertEqual(payslip._tanatech_period_wages(),
                         self._ancienne_base(employee))

    def test_g_base_survit_a_la_sortie_du_salarie(self):
        """Contrats clos en septembre : le bulletin d'août garde sa base.

        C'est le bug du 23/09/2026. L'ancienne formule tombait à zéro le jour où
        le salarié sortait, parce qu'elle lisait l'état du contrat au présent.
        """
        employee, declared, na_contract, payslip = self._salarie_deux_contrats(
            'Base Sorti Test Patty', state='close', date_end=date(2026, 9, 23))

        self.assertEqual(declared.state, 'close')
        self.assertEqual(na_contract.state, 'close')
        # L'ancienne formule ne trouve plus rien : c'est exactement le bug.
        self.assertEqual(self._ancienne_base(employee), 0.0)
        # La nouvelle base, elle, est celle de la période payée.
        self.assertEqual(payslip._tanatech_period_wages(), 400000.0)

    def test_g_contrat_termine_avant_la_periode_exclu(self):
        """Un contrat fini avant le mois payé ne compte pas."""
        employee = self._employee('Base Hors Periode Patty', self.company_tana)
        self._contract(employee, 300000.0, self.struct_sd, state='close',
                       date_end=date(2026, 6, 30))
        na_contract = self._contract(
            employee, 100000.0, self.struct_na, category='not_declared',
            state='close', date_end=date(2026, 6, 30))
        payslip = self._payslip(employee, na_contract, self.struct_na,
                                AOUT_DEBUT, AOUT_FIN)

        self.assertEqual(payslip._tanatech_period_wages(), 0.0)

    def test_g_renouvellement_ne_cumule_pas_deux_contrats_declares(self):
        """Renouvellement en cours de mois : un seul contrat déclaré compte.

        L'ancien contrat s'arrête le 14/08, le nouveau démarre le 15/08 : les
        deux chevauchent le bulletin d'août. Les additionner gonflerait la base
        de tout un salaire. Le plus récent l'emporte, ce que faisait déjà
        l'ancienne formule puisque l'ancien contrat y était exclu par son état.
        """
        employee = self._employee('Base Renouvellement Patty', self.company_tana)
        ancien = self._contract(
            employee, 200000.0, self.struct_sd, state='close',
            date_start=date(2020, 1, 1), date_end=date(2026, 8, 14))
        nouveau = self._contract(
            employee, 300000.0, self.struct_sd,
            date_start=date(2026, 8, 15))
        na_contract = self._contract(
            employee, 100000.0, self.struct_na, category='not_declared',
            source=nouveau)
        payslip = self._payslip(employee, na_contract, self.struct_na,
                                AOUT_DEBUT, AOUT_FIN)

        base = payslip._tanatech_period_wages()
        self.assertEqual(base, 400000.0,
                         "le nouveau contrat déclaré (300 000) plus le NA "
                         "(100 000), et surtout pas l'ancien en plus")
        self.assertNotEqual(base, 600000.0)
        self.assertEqual(base, self._ancienne_base(employee))

    def test_g_ferie_meme_montant_apres_la_sortie(self):
        """La règle jour férié donne le même montant, salarié sorti ou non.

        C'est le symptôme d'origine : 4,65 heures du 15/08 qui passaient de
        4 100 Ar à 0 au recalcul, une fois le salarié sorti.
        """
        rules = self.env['hr.salary.rule'].with_context(active_test=False).search([
            ('struct_id', '=', self.struct_na.id),
            ('code', '=', 'WORKONPUBLICHOLIDAYS'),
        ])
        if len(rules) != 1:
            self.skipTest(
                "La structure %r ne porte pas exactement une règle "
                "WORKONPUBLICHOLIDAYS (%s trouvée(s))."
                % (self.struct_na.name, len(rules)))
        self.assertIn(
            'PATTY_BASE', rules.amount_python_compute,
            "la migration 18.0.1.2.26 n'a pas basculé cette règle sur la base "
            "de la période : voir les logs « PATTY_BASE : » du build")

        heures = 4.65
        montants = {}
        for etiquette, state, fin in (('en cours', None, False),
                                      ('sorti', 'close', date(2026, 9, 23))):
            employee, declared, na_contract, payslip = self._salarie_deux_contrats(
                'Férié %s Test Patty' % etiquette, state=state, date_end=fin)
            montants[etiquette] = self._eval_rule(
                rules, employee, na_contract,
                payslip=payslip,
                worked_days={
                    'WORKONPUBLICHOLIDAYS': SimpleNamespace(
                        number_of_hours=heures),
                },
            )

        self.assertAlmostEqual(montants['sorti'], montants['en cours'], places=2,
                               msg="la sortie du salarié ne doit rien changer "
                                   "à un bulletin déjà payé")
        self.assertGreater(montants['sorti'], 0.0)
        # 0,5 x 4,65 x 400 000 / 173,33, la majoration seule posée en 1.2.24.
        self.assertAlmostEqual(montants['sorti'],
                               0.5 * heures * 400000.0 / 173.33, places=2)

    def test_g_migration_base_decouvre_et_reecrit(self):
        """La migration 18.0.1.2.26 reconnaît la ligne de base et la remplace.

        Fonction pure, sans base : le corps de la règle jour férié, les
        variantes de mise en forme, l'idempotence et les corps refusés.
        """
        migration = self._load_migration('18.0.1.2.26')
        ferie = (
            "wages = sum(employee.contract_ids.filtered(lambda c: c.state in "
            "['open', 'open_not_declared']).mapped('wage'))\n"
            "res = 0\n"
            "if worked_days.get(\"WORKONPUBLICHOLIDAYS\"):\n"
            "    total_amount = (worked_days.get(\"WORKONPUBLICHOLIDAYS\")"
            ".number_of_hours* wages / 173.33)\n"
            "    res = total_amount * 0.5\n"
            "result = res"
        )

        cible, motif = migration._transform(ferie)
        self.assertIsNone(motif)
        self.assertIn('PATTY_BASE', cible)
        self.assertIn('_tanatech_period_wages()', cible)
        self.assertNotIn('open_not_declared', cible)
        self.assertNotIn('__', cible)
        compile(cible, '<test>', 'exec')
        # Le reste du corps est intact : seule la ligne de base change.
        self.assertIn('total_amount * 0.5', cible)
        self.assertIn('173.33', cible)

        # Idempotence.
        self.assertEqual(migration._transform(cible), (None, None))

        # Mise en forme indifférente.
        for variante in (
            ferie.replace("['open', 'open_not_declared']",
                          '["open", "open_not_declared"]'),
            ferie.replace("lambda c: c.state", "lambda ct: ct.state"),
            ferie.replace("wages =", "base =").replace("* wages /", "* base /"),
        ):
            corps, motif = migration._transform(variante)
            self.assertIsNotNone(corps)
            self.assertIsNone(motif)

        # Une règle sans le motif n'est pas touchée.
        self.assertEqual(
            migration._transform("result = 3000 if employee.bank_account_id else 0"),
            (None, None))

        # Motif présent mais forme non reconnue : rien n'est écrit, motif donné.
        corps, motif = migration._transform(
            ferie.replace("employee.contract_ids", "employee.other_ids"))
        self.assertIsNone(corps)
        self.assertTrue(motif)

    # ------------------------------------------------------------------
    # Chargement du script de migration
    # ------------------------------------------------------------------

    @staticmethod
    def _load_migration(version='18.0.1.2.23'):
        """Le post-migrate de la version demandée, chargé par chemin.

        Le répertoire porte des points et le fichier un tiret : il n'est pas
        importable comme un module ordinaire.
        """
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'migrations', version, 'post-migrate.py')
        spec = importlib.util.spec_from_file_location(
            'migration_%s' % version.replace('.', '_'), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_migration_corps_cibles_compilent(self):
        """Les corps que la migration écrit dans les règles sont du Python
        valide, et appellent bien les méthodes du module.
        """
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
            "result = True\n" + migration._MISS_EXTRA_CONDITION,
        ]
        for body in bodies:
            compile(body, '<test>', 'exec')
            # safe_eval refuse tout nom contenant un double souligné : les corps
            # produits ne doivent en porter aucun.
            self.assertNotIn('__', body)

    def test_structures_resolues_par_nom(self):
        """Les structures utilisées par les tests sont bien celles de la base,
        retrouvées par nom et non par id.
        """
        self.assertTrue(self.struct_sd.id)
        self.assertTrue(self.struct_na.id)
        self.assertNotEqual(self.struct_sd, self.struct_na)
        self.assertEqual(_norm(self.struct_sd.name), _norm('Paie Régulière'))
        self.assertEqual(_norm(self.struct_na.name), _norm('Paie régulière NA'))
