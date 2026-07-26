# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields, _
import itertools
import logging

from datetime import date, datetime
import pytz


class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"

    work_entry_type_id = fields.Many2one("hr.work.entry.type", store=True)

    def _mark_conflicting_work_entries(self, start, stop):
        """ Surcharge : neutralise le conflit structurel entre les deux contrats
        miroirs d'un même employé (déclaré 'open' et non-déclaré
        'open_not_declared'), qui génèrent des entrées de travail sur des
        créneaux rigoureusement identiques et seraient donc systématiquement
        marquées en conflit par le core (qui ne joint que sur employee_id).

        On réécrit la requête du core à l'identique en y ajoutant deux LEFT JOIN
        sur hr_contract (hc1 sur b1.contract_id, hc2 sur b2.contract_id) et une
        clause excluant les paires miroirs. Le lien miroir est porté par le champ
        custom hr_contract.contract_id ('Source Contract'), renseigné sur le
        contrat NA et pointant vers le contrat SD.

        NULL-safe : le lien est unidirectionnel (renseigné côté NA seulement) et
        souvent NULL. Une clause NOT (hc1.contract_id = hc2.id OR hc2.contract_id
        = hc1.id) vaudrait NULL dès qu'un contract_id est NULL, et PostgreSQL
        traite une ligne dont le WHERE est NULL comme non retenue : la paire
        serait alors écartée de la détection à tort (faux négatif de conflit).
        On enveloppe donc chaque comparaison dans COALESCE(..., FALSE) = FALSE :
        lien absent (NULL) -> COALESCE rend FALSE -> la condition reste vraie et
        la paire est conservée pour la détection normale ; seule une égalité
        miroir avérée (TRUE) fait basculer COALESCE à TRUE et exclut la paire.
        """
        self.flush_model(['date_start', 'date_stop', 'employee_id', 'active'])
        query = """
            SELECT b1.id,
                   b2.id
              FROM hr_work_entry b1
              JOIN hr_work_entry b2
                ON b1.employee_id = b2.employee_id
               AND b1.id <> b2.id
         LEFT JOIN hr_contract hc1
                ON hc1.id = b1.contract_id
         LEFT JOIN hr_contract hc2
                ON hc2.id = b2.contract_id
             WHERE b1.date_start <= %(stop)s
               AND b1.date_stop >= %(start)s
               AND b1.active = TRUE
               AND b2.active = TRUE
               AND tsrange(b1.date_start, b1.date_stop, '()') && tsrange(b2.date_start, b2.date_stop, '()')
               AND COALESCE(hc1.contract_id = hc2.id, FALSE) = FALSE
               AND COALESCE(hc2.contract_id = hc1.id, FALSE) = FALSE
               AND {}
        """.format("b2.id IN %(ids)s" if self.ids else "b2.date_start <= %(stop)s AND b2.date_stop >= %(start)s")
        self.env.cr.execute(query, {"stop": stop, "start": start, "ids": tuple(self.ids)})
        conflicts = set(itertools.chain.from_iterable(self.env.cr.fetchall()))
        self.browse(conflicts).write({
            'state': 'conflict',
        })
        return bool(conflicts)

    def auto_update_overtime_work_entry_type(self):
        work_entries_to_unlink = self.env[self._name]
        for entry in self:
            date_start_tz = pytz.utc.localize(entry.date_start).astimezone(
                pytz.timezone(entry.employee_id._get_tz())
            )
            # overtimes = self.env['hr.attendance.overtime.with.datetimes'].search([('date', '=', date_start_tz.date())])
            overtimes = self.env["hr.attendance.overtime.with.datetimes"].search(
                [("attendance_id", "=", entry.attendance_id.id)]
            )
            work_entries_vals = []
            for overtime in overtimes:
                work_type_domain = []
                if overtime.overtime_type == "day_work_on_regular_day":
                    work_type_domain = [("code", "=", "DAYWORKONREGULARDAY")]
                elif overtime.overtime_type == "casual_night_work_on_regular_day":
                    work_type_domain = [("code", "=", "CASUALNIGHTWORKONREGULARDAY")]
                elif overtime.overtime_type == "occasional_night_work_on_weekends":
                    work_type_domain = [("code", "=", "OCCASIONALNIGHTWORKONWEEKENDS")]
                elif overtime.overtime_type == "day_work_on_sunday":
                    work_type_domain = [("code", "=", "DAYWORKONSUNDAY")]
                elif overtime.overtime_type == "night_work_on_sunday":
                    work_type_domain = [("code", "=", "NIGHTWORKONSUNDAY")]
                elif overtime.overtime_type == "work_on_public_holidays":
                    work_type_domain = [("code", "=", "WORKONPUBLICHOLIDAYS")]
                else:
                    work_type_domain = [("id", "=", 0)]
                work_entry_type = self.env["hr.work.entry.type"].search(
                    work_type_domain
                )
                date_start_utc = pytz.utc.localize(overtime.start_date).astimezone(
                    pytz.utc
                )
                date_stop_utc = pytz.utc.localize(overtime.end_date).astimezone(
                    pytz.utc
                )
                domain = [
                    ("date_start", "=", date_start_utc),
                    ("date_stop", "=", date_stop_utc),
                    ("employee_id", "=", overtime.employee_id.id),
                    ("contract_id", "=", overtime.employee_id.contract_id.id),
                    ("company_id", "=", overtime.employee_id.company_id.id),
                    ("attendance_id", "=", overtime.attendance_id.id),
                    ("state", "=", "draft"),
                ]
                if work_entry_type:
                    domain.append(("work_entry_type_id", "=", work_entry_type.id))
                if self.env["hr.work.entry"].search_count(domain):
                    continue

                date_start = pytz.utc.localize(overtime.start_date).astimezone(
                    pytz.timezone(overtime.employee_id._get_tz())
                )
                date_stop = pytz.utc.localize(overtime.end_date).astimezone(
                    pytz.timezone(overtime.employee_id._get_tz())
                )
                work_entries_vals.append(
                    {
                        "name": "%s: %s"
                        % (work_entry_type.name, overtime.employee_id.name),
                        "date_start": date_start.astimezone(pytz.utc).replace(
                            tzinfo=None
                        ),
                        "date_stop": date_stop.astimezone(pytz.utc).replace(
                            tzinfo=None
                        ),
                        "work_entry_type_id": (
                            work_entry_type.id if work_entry_type else False
                        ),
                        "employee_id": overtime.employee_id.id,
                        "contract_id": overtime.employee_id._get_nd_running_contract().id,
                        "company_id": overtime.employee_id.company_id.id,
                        "attendance_id": overtime.attendance_id.id,
                        "state": "draft",
                    }
                )
            start_of_day = datetime.combine(date_start_tz.date(), datetime.min.time())
            end_of_day = datetime.combine(date_start_tz.date(), datetime.max.time())

            # existing_work_entries = self.env['hr.work.entry'].search([('date_start', '>=', start_of_day), ('date_stop', '<=', end_of_day), ('work_entry_type_id.is_overtime', '=', True)])
            existing_work_entries = self.env["hr.work.entry"].search(
                [
                    ("attendance_id", "=", entry.attendance_id.id),
                    ("work_entry_type_id.is_overtime", "=", True),
                ]
            )
            work_entries_to_unlink |= existing_work_entries
            if work_entries_vals:
                self.env["hr.work.entry"].create(work_entries_vals)
        work_entries_to_unlink.write({"active": False})
        work_entries_to_unlink.unlink()

    def init(self):
        # FROM 7s by query to 2ms (with 2.6 millions entries)
        self.env.cr.execute(
            """
            CREATE INDEX IF NOT EXISTS hr_work_entry_contract_date_start_stop_idx
            ON hr_work_entry(contract_id, date_start, date_stop)
            WHERE state in ('draft', 'validated');
        """
        )

    def _init_column(self, column_name):
        if column_name != "contract_id":
            super()._init_column(column_name)
        else:
            self.env.cr.execute(
                """
                UPDATE hr_work_entry AS _hwe
                SET contract_id = result.contract_id
                FROM (
                    SELECT
                        hc.id AS contract_id,
                        array_agg(hwe.id) AS entry_ids
                    FROM
                        hr_work_entry AS hwe
                    LEFT JOIN
                        hr_contract AS hc
                    ON
                        hwe.employee_id=hc.employee_id AND
                        hc.state in ('open_not_declared', 'close') AND
                        hwe.date_start >= hc.date_start AND
                        hwe.date_stop < COALESCE(hc.date_end + integer '1', '9999-12-31 23:59:59')
                    WHERE
                        hwe.contract_id IS NULL
                    GROUP BY
                        hwe.employee_id, hc.id
                ) AS result
                WHERE _hwe.id = ANY(result.entry_ids)
            """
            )


class HrWorkEntryType(models.Model):
    _inherit = "hr.work.entry.type"

    is_overtime = fields.Boolean("Is overtime")
    is_readonly_code = fields.Boolean()
