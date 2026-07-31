# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields, _
import itertools
import logging

from datetime import date, datetime
import pytz

_logger = logging.getLogger(__name__)


class HrWorkEntry(models.Model):
    _inherit = "hr.work.entry"

    work_entry_type_id = fields.Many2one("hr.work.entry.type", store=True)

    def _get_undeclared_scope(self):
        """ Work entries belonging to the undeclared side of the mirror setup.

        The criterion is the contract, not the payroll structure: the contract is
        what a work entry is anchored on. Testing both contract_category AND
        state is deliberate — the category is the reference data, the
        'open_not_declared' state catches mirror contracts whose category was
        never filled in.
        """
        return self.filtered(
            lambda entry: entry.contract_id.contract_category == 'not_declared'
            or entry.contract_id.state == 'open_not_declared'
        )

    def action_validate(self):
        """ Override: only work entries of the declared side ever reach the
        'validated' state.

        The core exclusion constraint ('_work_entries_no_validated_conflict',
        hr_work_entry/models/hr_work_entry.py:55-65) forbids two validated and
        active work entries from overlapping for a single employee_id; the
        contract is not part of the exclusion key. Yet the two mirror contracts
        of one employee share the same working calendar and produce work entries
        on strictly identical time slots: validating them all raises a
        PostgreSQL ExclusionViolation, which no application-level code can catch
        up with.

        Why not simply restrict validation to the contract carrying the payslip:
        the NA payslip is a 'regular' payslip too as far as action_payslip_done
        is concerned (hr_payroll/models/hr_payslip.py:480), the NA structure
        being the default_struct_id of its own structure type — see
        _compute_struct_id, same file, line 1030. It therefore triggers the
        validation of ITS OWN entries in turn, which would collide with the ones
        the declared payslip has already validated. Batch validation is worse
        still: hr.payslip.run passes every payslip in a single call, the loop at
        lines 481-487 unions the recordsets and one single action_validate()
        writes the whole lot — both sides are then validated within the SAME
        transaction.

        So the cut is made at the only place that writes state='validated'
        through the ORM (hr_work_entry/models/hr_work_entry.py:113-124), which
        covers both paths at once. Overriding action_payslip_done would have
        meant copying its body over — the search at stake is hardcoded in the
        middle of the method, with no insertion point — hence breaking the
        inheritance chain, starting with hr_payroll_account, which generates the
        payslip's accounting entry.

        Undeclared work entries stay in 'draft'. That is already their state
        today, and it has no bearing on amounts: work hours
        (hr_payroll/models/hr_contract.py:344-393, _get_work_hours) and worked
        days (hr_payroll/models/hr_payslip.py:1143-1146) are both computed by
        filtering on the contract, never on the entry state.
        """
        undeclared = self._get_undeclared_scope()
        declared = self - undeclared
        if undeclared:
            _logger.info(
                "Work entry validation: %s undeclared entry(ies) kept out of "
                "the transition to 'validated'.",
                len(undeclared),
            )
        result = super(HrWorkEntry, declared).action_validate()
        if declared and not result:
            # The core returns False without validating anything and without
            # raising: without this trace, a leftover conflict on the declared
            # side would let the payslip reach 'done' while silently leaving the
            # whole batch unvalidated.
            _logger.warning(
                "Work entry validation: failed on the declared side (leftover "
                "overlap or entry without a work entry type). None of the %s "
                "entry(ies) was validated; ids=%s",
                len(declared), declared.ids[:50],
            )
        return result

    def _mark_conflicting_work_entries(self, start, stop):
        """ Override: neutralises the structural conflict between the two mirror
        contracts of one employee (declared 'open' and undeclared
        'open_not_declared'), which generate work entries on strictly identical
        time slots and would therefore be systematically marked as conflicting by
        the core (which only joins on employee_id).

        The core query is rewritten as-is, with two extra LEFT JOINs on
        hr_contract (hc1 on b1.contract_id, hc2 on b2.contract_id) and a clause
        excluding mirror pairs. The mirror link is carried by the custom
        hr_contract.contract_id field ('Source Contract'), set on the NA contract
        and pointing at the SD one.

        NULL-safe: the link is one-way (set on the NA side only) and often NULL.
        A NOT (hc1.contract_id = hc2.id OR hc2.contract_id = hc1.id) clause would
        evaluate to NULL as soon as one contract_id is NULL, and PostgreSQL
        discards rows whose WHERE evaluates to NULL: the pair would then be
        wrongly dropped from detection (false negative). Each comparison is
        therefore wrapped in COALESCE(..., FALSE) = FALSE: a missing link (NULL)
        makes COALESCE return FALSE, so the condition stays true and the pair is
        kept for normal detection; only a proven mirror equality (TRUE) flips
        COALESCE to TRUE and excludes the pair.

        Second safety net, independent of data quality: detection is restricted
        to pairs on the SAME side (contract_category). The hr_contract.contract_id
        mirror link is only set on the NA side and may be missing; a mirror pair
        orphaned from that link would still be marked as conflicting,
        _check_if_error would return True and action_validate would give up —
        without raising, hence silently — on validating the WHOLE recordset, that
        is the entire batch under grouped validation. One badly paired contract
        would be enough to validate nothing out of the 566 payslips.

        This second net cannot hide a conflict that would actually matter: since
        action_validate above only lets the declared side reach 'validated', an
        overlap across sides can by construction never be submitted to the
        exclusion constraint. Overlaps within one side remain fully detected.
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
               AND COALESCE(hc1.contract_category, 'declared') = COALESCE(hc2.contract_category, 'declared')
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
