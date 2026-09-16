# -*- coding:utf-8 -*-
from datetime import datetime, time, timedelta

import logging
import pytz

from odoo import api, Command, models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Dimanche, au sens de datetime.date.weekday().
_SUNDAY = 6

# Lignes SORTIES de l'assiette d'arrondi SALARR (règle C, arbitrage Patty).
#
# L'arrondi au multiple de 5 000 Ar porte sur le net augmenté des accessoires,
# MOINS ce qui est listé ici. Les frais de tenue de compte (FRAISBANC, 3 000 Ar)
# sont refacturés à l'identique : les arrondir n'a pas de sens, et le client veut
# retrouver ses 3 000 Ar intacts après l'arrondi.
#
#   net 300 000 + frais 3 000  ->  arrondi sur 300 000  ->  303 000 versés.
#
# Les allocations familiales (ALLOC) RESTENT dans l'assiette : c'est la consigne
# écrite reçue. Pour les en sortir, il suffit d'ajouter "ALLOC" à ce tuple —
# aucune migration, aucun bump de manifeste. L'écart entre les deux options est
# mesuré par le test ``test_c_arrondi_alloc_hors_assiette``.
FRAIS_HORS_ARRONDI = ("FRAISBANC",)

# Pas d'arrondi du salaire net, et son demi-pas (arrondi au plus proche).
ARRONDI_PAS = 5000
ARRONDI_DEMI_PAS = 2500


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    is_undeclared_payslip = fields.Boolean('Is undeclared payslip ?', compute="_define_payslip_nature", default=False,
                                           store=False)

    @api.depends('contract_id')
    def _define_payslip_nature(self):
        for payslip in self:
            payslip.is_undeclared_payslip = False
            if payslip.contract_id and payslip.contract_id.contract_category == 'not_declared':
                payslip.is_undeclared_payslip = True

    is_nd_ticket_payslip = fields.Boolean(
        'Prints the NA 80mm ticket ?', compute="_compute_is_nd_ticket_payslip", store=False)

    @api.depends('contract_id', 'struct_id', 'struct_id.is_stc')
    def _compute_is_nd_ticket_payslip(self):
        # Only undeclared payslips whose structure is NOT routed to report_final_settlement
        # (i.e. struct_id.is_stc is False) keep the dedicated 80mm "PAIEMENT" ticket
        # (report_nd_payslip). This mirrors the exact criterion used by _get_pdf_reports,
        # so the STC NA structure (flagged is_stc) is excluded and follows the standard
        # flow like declared payslips.
        for payslip in self:
            undeclared = bool(payslip.contract_id and payslip.contract_id.contract_category == 'not_declared')
            payslip.is_nd_ticket_payslip = undeclared and not payslip.struct_id.is_stc

    overtime_hours_count = fields.Float(compute='_compute_overtime_hours')

    employee_id = fields.Many2one(
        'hr.employee', required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), '|', ('active', '=', True), ('active', '=', False)]")

    def _compute_contract_domain_ids(self):
        for payslip in self:
            payslip.contract_domain_ids = self.env['hr.contract'].search([
                ('company_id', '=', payslip.company_id.id),
                ('employee_id', '=', payslip.employee_id.id),
                ('state', 'in', ['open', 'open_not_declared', 'close']),
            ])

    def action_print_nd_payslip(self):
        return self.env.ref('tanatech_hr_payroll.action_report_nd_payslip').report_action(self)

    def action_open_overtime(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Overtime This Month'),
            'view_mode': 'list,form',
            'res_model': 'hr.attendance.overtime.with.datetimes',
            'domain': [('employee_id', '=', self.employee_id.id), ('date', '>=', self.date_from),
                       ('date', '<=', self.date_to)],
            'context': "{'create': False}",
        }

    @api.depends('date_from', 'date_to', 'employee_id.overtime_with_datetimes_ids.duration',
                 'employee_id.attendance_ids')
    def _compute_overtime_hours(self):
        for payslip in self:
            mapped_validated_overtimes = dict(self.env['hr.attendance.overtime.with.datetimes']._read_group(
                domain=[('date', '>=', payslip.date_from), ('date', '<=', payslip.date_to)],
                groupby=['employee_id'],
                aggregates=['duration:sum']
            ))
            payslip.overtime_hours_count = mapped_validated_overtimes.get(payslip.employee_id, 0)

    def compute_sheet(self):
        # generate_work_entries(force=True) court-circuite le garde-fou
        # date_generated_from/to et NE supprime PAS l'existant : sans nettoyage
        # préalable, chaque recalcul de bulletin empile un jeu complet d'entrées
        # de travail identiques (doublons). On reproduit donc le pattern
        # d'archivage de hr_attendance._regenerate_work_entries : archiver avant
        # de régénérer.
        #
        # Déduplication des couples (employee_id, date_from, date_to) : lors d'un
        # calcul par lot, la fiche SD et sa jumelle NA portent le même employé et
        # la même période ; sans cela elles déclencheraient deux fois le même
        # archivage + régénération (redondant, quoique idempotent).
        seen = set()
        for slip in self:
            key = (slip.employee_id.id, slip.date_from, slip.date_to)
            if key in seen:
                continue
            seen.add(key)

            # Même source de vérité que hr_employee.generate_work_entries pour la
            # liste d'états : on archive exactement l'ensemble qui va être
            # régénéré (ni les entrées SD légitimes en 'open', ni les entrées
            # hors période, ni les entrées déjà validées).
            contracts = slip.employee_id._get_contracts(
                slip.date_from,
                slip.date_to,
                states=["open_not_declared", "close"],
            )
            work_entries = self.env['hr.work.entry'].search([
                ('contract_id', 'in', contracts.ids),
                ('date_stop', '>=', datetime.combine(slip.date_from, time.min)),
                ('date_start', '<=', datetime.combine(slip.date_to, time.max)),
                ('state', '!=', 'validated'),
            ])
            work_entries.write({'active': False})

            slip.employee_id.generate_work_entries(
                slip.date_from,
                slip.date_to,
                force=True,
            )

        return super().compute_sheet()

    def _filter_nd_ticket_payslips(self):
        """ Monthly NA payslips: undeclared structure category and not routed to
        the final settlement report. They must only be printed through their
        dedicated 80mm ticket (action_print_nd_payslip). """
        return self.filtered(
            lambda slip: slip.struct_id.type_id.structure_category == 'not_declared'
            and not slip.struct_id.is_stc
        )

    def action_print_payslip(self):
        # Guard raised here and not in _get_pdf_reports: that one is also called
        # by _generate_pdf on payslip confirmation, where a UserError would block
        # the validation of an ND-only batch. Here the server action / form button
        # runs in a regular RPC, so the error shows up as a clean dialog instead
        # of the empty zero-page PDF the /print/payslips controller would return.
        printable_payslips = self - self._filter_nd_ticket_payslips()
        if not printable_payslips:
            raise UserError(_(
                "Aucun bulletin A4 dans la sélection. Pour les bulletins NA, "
                "utilisez « Imprimer les tickets (NA) »."
            ))
        return super(HrPayslip, printable_payslips).action_print_payslip()

    def action_print_nd_tickets(self):
        # Grouped counterpart of the form ticket button (action_print_nd_payslip):
        # same report action, so same 80mm paperformat and template — the template
        # iterates over docs, one merged PDF comes out natively.
        nd_ticket_payslips = self._filter_nd_ticket_payslips()
        if not nd_ticket_payslips:
            raise UserError(_("Aucun bulletin NA dans la sélection."))
        return self.env.ref('tanatech_hr_payroll.action_report_nd_payslip').report_action(nd_ticket_payslips)

    def _get_pdf_reports(self):
        # Route every STC payslip (struct_id.is_stc) to the final settlement
        # report, whatever the size of the print batch: this method is the single
        # routing point of the /print/payslips flow (form button and list server
        # action), so the reroute must not be restricted to single-slip prints.
        # The is_stc flag matches both STC structures (SD and NA) and is kept in
        # sync with _compute_is_nd_ticket_payslip.
        # Monthly NA payslips are dropped from the mapping: they must never come
        # out of a batch print nor get the standard A4 slip attached on
        # confirmation — their 80mm ticket is the only printable form.
        res = super()._get_pdf_reports()

        final_settlement_template = self.env.ref('tanatech_hr_payroll.action_report_final_settlement')
        stc_payslips = self.filtered(lambda slip: slip.struct_id.is_stc)
        nd_ticket_payslips = self._filter_nd_ticket_payslips()
        if not stc_payslips and not nd_ticket_payslips:
            return res

        for report in list(res.keys()):
            remaining = res[report] - nd_ticket_payslips
            if report != final_settlement_template:
                remaining -= stc_payslips
            if remaining:
                res[report] = remaining
            else:
                # No slip left on this report: drop the entry so no empty PDF
                # rendering is triggered downstream.
                del res[report]
        if stc_payslips:
            res[final_settlement_template] |= stc_payslips

        return res

    # ==================================================================
    # Décomptes ramenés du corps des règles vers le module
    # ==================================================================
    #
    # Historiquement tout le calcul vit dans hr.salary.rule.amount_python_compute,
    # c'est-à-dire dans des enregistrements en base modifiés par scripts de
    # migration : pas de relecture en PR, pas de test, et la même logique
    # recopiée sur quatre structures qui divergent au fil des correctifs. Les
    # trois décomptes qui viennent d'être arbitrés par le client reviennent donc
    # ici, et les règles n'ont plus qu'un appel d'une ligne :
    #
    #   payslip.env['hr.payslip'].browse(payslip.id)._tanatech_leave_days('LEAVE120')
    #
    # Le browse n'est pas une coquetterie. Dans le localdict des règles, la
    # variable « payslip » est un objet ENVELOPPE du moteur de paie (Payslips),
    # pas un enregistrement. L'enveloppe relaie les accès d'attribut vers
    # l'enregistrement — les règles en production lisent déjà payslip.env,
    # payslip.date_from et payslip.date_to à travers elle — mais repasser
    # explicitement par browse garantit un vrai recordset, donc l'accès aux
    # méthodes du module, quelle que soit la forme exacte de l'enveloppe dans la
    # version installée. La migration 18.0.1.2.23 SONDE ce point sur la base
    # cible et n'écrit aucune règle si l'appel n'y est pas praticable.

    # ------------------------------------------------------------------
    # Congés : jours de paie
    # ------------------------------------------------------------------

    def _tanatech_leave_dates(self, work_entry_code):
        """Les dates de congé validé du salarié qui tombent dans la période du
        bulletin, avec le poids de chaque date.

        Renvoie un dict {date -> poids}, le poids valant 1.0 pour une journée
        entière et 0.5 pour une demi-journée. Un même jour couvert par deux
        congés n'est compté qu'une fois, au plus lourd des deux : hr_holidays
        interdit déjà deux congés qui se chevauchent pour un même salarié, mais
        un doublon de saisie ne doit en aucun cas payer le jour deux fois.
        """
        self.ensure_one()
        weights = {}
        if not self.date_from or not self.date_to:
            return weights

        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.work_entry_type_id.code', '=', work_entry_code),
            ('request_date_from', '<=', self.date_to),
            ('request_date_to', '>=', self.date_from),
        ])
        for leave in leaves:
            start = max(leave.request_date_from, self.date_from)
            stop = min(leave.request_date_to, self.date_to)
            if stop < start:
                continue
            # request_unit_half est le drapeau de demi-journée de hr_holidays ;
            # il n'existe que sur un congé d'UNE seule journée. Le repli sur
            # number_of_days couvre une base où le drapeau ne serait pas posé.
            half = bool(getattr(leave, 'request_unit_half', False))
            if not half and start == stop and leave.request_date_from == leave.request_date_to:
                half = float(leave.number_of_days or 0.0) == 0.5
            weight = 0.5 if half else 1.0

            day = start
            while day <= stop:
                if weights.get(day, 0.0) < weight:
                    weights[day] = weight
                day += timedelta(days=1)
        return weights

    def _tanatech_public_holidays(self):
        """Les dates de jour férié applicables au salarié sur la période.

        Un jour férié est un ``resource.calendar.leaves`` SANS ressource
        (``resource_id`` vide : il vaut pour tout le monde) dont la société est
        celle du salarié ou vide. Le 15/08 existe une fois par société : passer
        par un ensemble de dates neutralise le doublon sans avoir à choisir
        laquelle des trois lignes est la bonne.

        Le stockage est en Datetime UTC, et les deux conventions de saisie se
        rencontrent en base (00:00->23:59 UTC, ou 21:00 J-1 -> 20:59 J en heure
        locale). On teste donc si MIDI LOCAL de chaque jour tombe dans
        l'intervalle : les deux conventions donnent alors le même jour, et
        aucune ne déborde sur la veille ou le lendemain.
        """
        self.ensure_one()
        holidays = set()
        if not self.date_from or not self.date_to:
            return holidays

        company = self.employee_id.company_id or self.company_id
        entries = self.env['resource.calendar.leaves'].search([
            ('resource_id', '=', False),
            ('date_from', '<=', datetime.combine(self.date_to, time.max)),
            ('date_to', '>=', datetime.combine(self.date_from, time.min)),
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ])
        if not entries:
            return holidays

        default_tz = self.employee_id.tz or self.env.user.tz or 'UTC'
        day = self.date_from
        while day <= self.date_to:
            for entry in entries:
                tz_name = entry.calendar_id.tz or default_tz
                try:
                    tz = pytz.timezone(tz_name)
                except pytz.UnknownTimeZoneError:
                    tz = pytz.UTC
                noon = tz.localize(
                    datetime.combine(day, time(12, 0))
                ).astimezone(pytz.UTC).replace(tzinfo=None)
                if entry.date_from <= noon <= entry.date_to:
                    holidays.add(day)
                    break
            day += timedelta(days=1)
        return holidays

    def _tanatech_leave_days(self, work_entry_code):
        """Jours de congé PAYÉS sur la période du bulletin (règle A).

        Méthode client, arbitrage Patty : chaque jour couvert par le congé
        compte 1, sauf le dimanche (0) et le jour férié (0). Le samedi compte 1.
        Une demi-journée compte 0,5.

        Sert CPDED (retenue au taux ordinaire) et CPALLOC (indemnité au taux
        congé) des structures de paie régulière, déclarée et NA. Les structures
        de solde de tout compte ne l'utilisent pas : elles indemnisent le solde
        ACQUIS ET NON PRIS (migration 18.0.1.2.19) et ne comptent aucun jour posé.
        """
        self.ensure_one()
        weights = self._tanatech_leave_dates(work_entry_code)
        if not weights:
            return 0.0
        holidays = self._tanatech_public_holidays()
        total = 0.0
        for day, weight in weights.items():
            if day.weekday() == _SUNDAY or day in holidays:
                continue
            total += weight
        return total

    def _tanatech_calendar_leave_days(self, work_entry_code, cap=None):
        """Jours CALENDAIRES de congé sur la période, éventuellement plafonnés.

        Rien n'est déduit ici : ni dimanche, ni jour férié. C'est le décompte
        des congés forfaitaires — la maternité (MATOFF) est indemnisée à demi
        salaire sur 30 jours calendaires, week-ends et fériés compris.

        ``cap`` plafonne le décompte (30 pour MATOFF) : un congé de maternité
        s'étale sur plusieurs bulletins, le plafond s'applique donc aux jours
        retenus SUR CE BULLETIN, exactement comme le ``min(mat_days, 30)`` de la
        règle de la structure déclarée qu'on reproduit ici.
        """
        self.ensure_one()
        weights = self._tanatech_leave_dates(work_entry_code)
        total = float(sum(weights.values()))
        if cap is not None:
            total = min(total, float(cap))
        return total

    # ------------------------------------------------------------------
    # Arrondi du net à payer
    # ------------------------------------------------------------------

    def _tanatech_rule_total(self, result_rules, code):
        """Le total DÉJÀ CALCULÉ d'une règle de ce bulletin, lu dans le
        localdict, ou 0.0 si la règle ne s'est pas déclenchée.

        ``result_rules`` est l'objet browsable que le moteur de paie alimente au
        fil des règles. Sa forme interne n'est pas une API publique et a bougé
        entre versions : on sonde donc les trois formes connues plutôt que d'en
        parier une. Ce code tourne en Python normal (module), pas sous
        safe_eval : ``getattr`` et ``isinstance`` y sont disponibles.

        Une règle non déclenchée n'a pas d'entrée : 0.0 est alors la bonne
        réponse, pas une erreur — un salarié sans compte bancaire n'a pas de
        ligne FRAISBANC et il n'y a rien à sortir de son assiette.
        """
        if result_rules is None:
            return 0.0

        entry = None
        # Forme courante : un dict {code -> {'total', 'amount', 'quantity'}}
        # porté par l'attribut .dict de l'objet browsable.
        container = getattr(result_rules, 'dict', None)
        if isinstance(container, dict):
            entry = container.get(code)
        if entry is None and isinstance(result_rules, dict):
            entry = result_rules.get(code)
        if entry is None:
            # Forme attribut : result_rules.FRAISBANC.total
            entry = getattr(result_rules, code, None)

        if entry is None:
            return 0.0
        if isinstance(entry, dict):
            return float(entry.get('total') or 0.0)
        total = getattr(entry, 'total', None)
        if isinstance(total, (int, float)):
            return float(total)
        if isinstance(entry, (int, float)):
            return float(entry)
        return 0.0

    def _tanatech_rounding_exclusion(self, result_rules):
        """Le montant à SORTIR de l'assiette d'arrondi, sur ce bulletin.

        Somme des totaux des règles listées dans ``FRAIS_HORS_ARRONDI``.
        """
        self.ensure_one()
        return sum(
            self._tanatech_rule_total(result_rules, code)
            for code in FRAIS_HORS_ARRONDI
        )

    def _tanatech_rounding_adjustment(self, to_pay, result_rules=None):
        """L'ajustement d'arrondi SALARR (règle C).

        ``to_pay`` est l'assiette telle que la règle la construit en base
        (NET + OPCOMP + AJUST) : elle est passée telle quelle, ce script ne la
        reconstruit pas. On en retire les lignes hors assiette, on arrondit au
        multiple de 5 000 le plus proche, et on renvoie l'écart.

        SALNETAP (séquence 11000) somme ensuite NET + OPCOMP + AJUST, donc le
        net arrondi PLUS les frais sortis de l'assiette : les 3 000 Ar de frais
        se retrouvent intacts sur le net à payer, sans second arrondi.
        """
        self.ensure_one()
        base = float(to_pay or 0.0) - self._tanatech_rounding_exclusion(result_rules)
        target = ((int(round(base)) + ARRONDI_DEMI_PAS) // ARRONDI_PAS) * ARRONDI_PAS
        return target - base

    # ------------------------------------------------------------------
    # Prime de mission
    # ------------------------------------------------------------------

    def _tanatech_declared_contract(self):
        """Le contrat DÉCLARÉ du salarié du bulletin, ou un recordset vide.

        Le contrat NA est une copie du contrat déclaré et pointe vers lui par
        ``contract_id`` : c'est le chemin sûr. À défaut (contrat NA orphelin,
        bulletin porté par le contrat déclaré lui-même), on cherche le contrat
        déclaré du salarié qui couvre la période du bulletin, puis le plus
        récent.
        """
        self.ensure_one()
        contract = self.contract_id
        if contract.contract_category == 'declared':
            return contract
        if contract.contract_id and contract.contract_id.contract_category == 'declared':
            return contract.contract_id

        declared = self.env['hr.contract'].with_context(active_test=False).search([
            ('employee_id', '=', self.employee_id.id),
            ('contract_category', '=', 'declared'),
        ], order='date_start desc')
        if not declared:
            return declared
        covering = declared.filtered(
            lambda c: (not self.date_to or not c.date_start or c.date_start <= self.date_to)
            and (not self.date_from or not c.date_end or c.date_end >= self.date_from)
        )
        return (covering or declared)[0]

    def _tanatech_mission_eligible(self):
        """Le salarié est-il éligible à la prime de mission (règle D) ?

        Non si la case est décochée sur le contrat du bulletin, non plus si elle
        l'est sur le contrat DÉCLARÉ du même salarié. La prime est versée sur
        les structures NA ; or le contrat NA est une copie du contrat déclaré
        dont les écritures ultérieures ne sont propagées que pour une liste
        fermée de champs (tanatech_hr_contract.HrContract.write). Décocher la
        case sur le contrat déclaré doit donc suffire, sinon le client devrait
        penser à la décocher deux fois pour chaque salarié.
        """
        self.ensure_one()
        contract = self.contract_id
        if contract and not contract.tanatech_mission_eligible:
            return False
        declared = self._tanatech_declared_contract()
        if declared and not declared.tanatech_mission_eligible:
            return False
        return True
