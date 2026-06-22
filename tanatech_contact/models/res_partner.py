# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from lxml import etree


class ResPartner(models.Model):
    _inherit = "res.partner"

    # New fields
    client_code = fields.Char(string="Code Client", copy=False, readonly=True)

    # Re-declare Studio fields to ensure they exist and can be safely validated
    x_studio_nif_1 = fields.Char(string="NIF")
    x_studio_char_field_d3loF = fields.Char(string="STAT")

    _sql_constraints = [
        ("client_code_uniq", "unique(client_code)", "Le Code Client doit être unique !")
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("client_code"):
                company_id = vals.get("company_id")
                # Fill the first available gap instead of always incrementing
                vals["client_code"] = self._get_next_available_client_code(company_id)
        return super().create(vals_list)

    def unlink(self):
        # Group affected partners by company before deletion, since we need
        # to realign each company's sequence separately afterward
        company_ids = set(self.mapped("company_id").ids) or {False}
        res = super().unlink()
        for company_id in company_ids:
            self._realign_client_code_sequence(company_id or False)
        return res

    @api.depends("name", "client_code")
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get("show_client_code_only"):
            for partner in self:
                partner.display_name = partner.client_code or _("[Pas de code]")

    @api.model
    def _name_search(
        self, name, args=None, operator="ilike", limit=100, name_get_uid=None
    ):
        args = args or []
        if name:
            domain = ["|", ("name", operator, name), ("client_code", operator, name)]
            return self._search(
                domain + args, limit=limit, access_rights_uid=name_get_uid
            )
        return super(ResPartner, self)._name_search(
            name, args=args, operator=operator, limit=limit, name_get_uid=name_get_uid
        )

    # ----------------------------------------
    # Sequence helpers
    # ----------------------------------------

    @api.model
    def _get_sequence_for_company(self, company_id=False):
        domain = [("code", "=", "res.partner.client.code")]
        domain += (
            [("company_id", "=", company_id)]
            if company_id
            else [("company_id", "=", False)]
        )
        sequence = self.env["ir.sequence"].search(domain, limit=1)
        if not sequence and company_id:
            # Fallback to the default (no-company) sequence if none exists yet
            sequence = self.env["ir.sequence"].search(
                [("code", "=", "res.partner.client.code"), ("company_id", "=", False)],
                limit=1,
            )
        return sequence

    @api.model
    def _get_existing_client_code_numbers(self, prefix, company_id=False):
        domain = [("client_code", "!=", False)]
        domain += (
            [("company_id", "=", company_id)]
            if company_id
            else [("company_id", "=", False)]
        )
        partners = self.env["res.partner"].sudo().search(domain)
        numbers = set()
        for partner in partners:
            code = partner.client_code
            if code and code.startswith(prefix):
                num_part = code[len(prefix) :]
                if num_part.isdigit():
                    numbers.add(int(num_part))
        return numbers

    @api.model
    def _get_next_available_client_code(self, company_id=False):
        """Return the lowest unused client code number for the given
        company, filling gaps left by deleted or merged partners.
        Falls back to the sequence counter if no gap is available."""
        sequence = self._get_sequence_for_company(company_id)
        if not sequence:
            return "/"

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0
        existing_numbers = self._get_existing_client_code_numbers(prefix, company_id)

        candidate = 1
        while candidate in existing_numbers:
            candidate += 1

        new_code = f"{prefix}{str(candidate).zfill(padding)}"

        if candidate >= sequence.number_next_actual:
            sequence.number_next = candidate + 1

        return new_code

    @api.model
    def _realign_client_code_sequence(self, company_id=False):
        """Reset the sequence pointer to just after the highest remaining
        client code for this company, so deleted/merged codes are
        picked up again instead of leaving a permanent gap at the end."""
        sequence = self._get_sequence_for_company(company_id)
        if not sequence:
            return

        prefix = sequence.prefix or ""
        existing_numbers = self._get_existing_client_code_numbers(prefix, company_id)
        max_number = max(existing_numbers, default=0)

        if sequence.number_next_actual != max_number + 1:
            sequence.number_next = max_number + 1

    # ----------------------------------------
    # Maintenance action
    # ----------------------------------------

    def action_assign_client_code(self):
        """Maintenance action: assign a client code to partners that don't
        have one yet (e.g. legacy data created before this module, or
        imported records). Fills the lowest available gap."""
        for partner in self:
            if not partner.client_code:
                partner.client_code = partner._get_next_available_client_code(
                    partner.company_id.id
                )

    # ----------------------------------------
    # View customization for Studio fields
    # ----------------------------------------

    @api.model
    def get_views(self, views, options=None):
        res = super().get_views(views, options=options)
        if "form" in res["views"]:
            # Dynamically set required="is_company" for the studio fields in the UI
            arch = etree.fromstring(res["views"]["form"]["arch"])
            modified = False
            for field_name in ["x_studio_nif_1", "x_studio_char_field_d3loF"]:
                for node in arch.xpath(f"//field[@name='{field_name}']"):
                    node.set("required", "is_company")
                    modified = True
            if modified:
                res["views"]["form"]["arch"] = etree.tostring(arch, encoding="unicode")
        return res

    @api.model
    def cron_backfill_client_codes(self):
        """Scheduled action: backfill client_code for all partners missing
        one, scoped per company, using raw SQL for performance on large
        datasets. Also realigns each company's sequence afterward."""

        # Step 1: backfill partners that belong to a company
        self.env.cr.execute("""
            WITH company_prefix AS (
                SELECT id AS company_id,
                    CASE name
                        WHEN 'TANATECH' THEN 'TAN'
                        WHEN 'MASONTSIKA' THEN 'MAS'
                        WHEN 'STUDYDAS' THEN 'STD'
                        ELSE 'CL'
                    END AS prefix
                FROM res_company
            ),
            existing_max AS (
                SELECT p.company_id, cp.prefix,
                    COALESCE(MAX(
                        CASE WHEN p.client_code ~ ('^' || cp.prefix || '[0-9]+$')
                            THEN substring(p.client_code FROM length(cp.prefix) + 1)::int
                        END
                    ), 0) AS max_num
                FROM res_partner p
                JOIN company_prefix cp ON cp.company_id = p.company_id
                GROUP BY p.company_id, cp.prefix
            ),
            to_fill AS (
                SELECT p.id, p.company_id,
                    ROW_NUMBER() OVER (PARTITION BY p.company_id ORDER BY p.create_date, p.id) AS rn
                FROM res_partner p
                WHERE p.client_code IS NULL
                AND p.company_id IS NOT NULL
            )
            UPDATE res_partner p
            SET client_code = cp.prefix || LPAD((COALESCE(em.max_num, 0) + tf.rn)::text, 5, '0')
            FROM to_fill tf
            JOIN company_prefix cp ON cp.company_id = tf.company_id
            LEFT JOIN existing_max em ON em.company_id = tf.company_id
            WHERE p.id = tf.id;
        """)

        # Step 2: backfill partners with no company (fallback prefix "CL")
        self.env.cr.execute("""
            WITH existing_max_nocompany AS (
                SELECT COALESCE(MAX(
                    CASE WHEN client_code ~ '^CL[0-9]+$'
                        THEN substring(client_code FROM 3)::int
                    END
                ), 0) AS max_num
                FROM res_partner
                WHERE company_id IS NULL
            ),
            to_fill_nocompany AS (
                SELECT id,
                    ROW_NUMBER() OVER (ORDER BY create_date, id) AS rn
                FROM res_partner
                WHERE client_code IS NULL
                AND company_id IS NULL
            )
            UPDATE res_partner p
            SET client_code = 'CL' || LPAD((em.max_num + tf.rn)::text, 5, '0')
            FROM to_fill_nocompany tf, existing_max_nocompany em
            WHERE p.id = tf.id;
        """)

        # Step 3: realign per-company sequences so future codes continue logically
        self.env.cr.execute("""
            UPDATE ir_sequence seq
            SET number_next = sub.max_num + 1
            FROM (
                SELECT
                    cp.id AS company_id,
                    cp.prefix,
                    COALESCE(MAX(
                        CASE WHEN p.client_code ~ ('^' || cp.prefix || '[0-9]+$')
                            THEN substring(p.client_code FROM length(cp.prefix) + 1)::int
                        END
                    ), 0) AS max_num
                FROM (
                    SELECT id,
                        CASE name
                            WHEN 'TANATECH' THEN 'TAN'
                            WHEN 'MASONTSIKA' THEN 'MAS'
                            WHEN 'STUDYDAS' THEN 'STD'
                            ELSE 'CL'
                        END AS prefix
                    FROM res_company
                ) cp
                LEFT JOIN res_partner p ON p.company_id = cp.id
                GROUP BY cp.id, cp.prefix
            ) sub
            WHERE seq.code = 'res.partner.client.code'
            AND seq.company_id = sub.company_id;
        """)

        # Step 4: realign the fallback (no-company) sequence
        self.env.cr.execute("""
            UPDATE ir_sequence
            SET number_next = (
                SELECT COALESCE(MAX(substring(client_code FROM 3)::int), 0) + 1
                FROM res_partner
                WHERE client_code ~ '^CL[0-9]+$' AND company_id IS NULL
            )
            WHERE code = 'res.partner.client.code' AND company_id IS NULL;
        """)
