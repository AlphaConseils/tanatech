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

    # _sql_constraints = [
    #     ("client_code_uniq", "unique(client_code)", "Le Code Client doit être unique !")
    # ]

    @api.onchange("company_id")
    def _onchange_company_id_client_code(self):
        """Preview the client_code that will be assigned once the record
        is saved, based on the newly selected company's sequence.
        This does NOT consume a sequence number — it's a non-destructive
        preview only; the real number is taken on write()/create()."""
        if not self.company_id:
            return
        sequence = self._get_sequence_for_company(self.company_id.id)
        if not sequence:
            return

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0
        next_number = sequence.number_next_actual

        self.client_code = f"{prefix}{str(next_number).zfill(padding)}"

    @api.model
    def _get_next_sequence_client_code(self, company_id=False):
        """Return the next available client code for the given company's sequence,
        ensuring uniqueness across all partners."""
        sequence = self._get_sequence_for_company(company_id)
        if not sequence:
            return "/"

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0
        candidate = sequence.number_next_actual

        # Vérifier que le code n'existe pas déjà (toutes sociétés confondues)
        max_attempts = 1000  # Sécurité pour éviter une boucle infinie
        for _ in range(max_attempts):
            new_code = f"{prefix}{str(candidate).zfill(padding)}"
            
            # Vérifier si ce code existe déjà dans la base
            existing = self.sudo().search([('client_code', '=', new_code)], limit=1)
            if not existing:
                sequence.number_next = candidate + 1
                return new_code
            candidate += 1
        
        raise ValidationError(_("Impossible de générer un code client unique après %s tentatives.") % max_attempts)

    @api.model_create_multi
    def create(self, vals_list):
        # Track codes assigned within this same create() call, since
        # records aren't in DB yet and won't be seen by a fresh query.
        reserved_numbers_by_company = {}

        for vals in vals_list:
            if not vals.get("client_code"):
                company_id = vals.get("company_id")
                reserved = reserved_numbers_by_company.setdefault(company_id, set())
                code, number = self._get_next_available_client_code(
                    company_id, exclude_numbers=reserved
                )
                vals["client_code"] = code
                if number is not None:
                    reserved.add(number)
        return super().create(vals_list)

    def write(self, vals):
        if self.env.context.get("skip_client_code_company_sync"):
            return super().write(vals)

        company_changes = {}
        if "company_id" in vals:
            new_company_id = vals.get("company_id") or False
            for partner in self:
                old_company_id = partner.company_id.id or False
                if old_company_id != new_company_id:
                    company_changes[partner.id] = old_company_id

        res = super().write(vals)

        if company_changes:
            new_company_id = vals.get("company_id") or False
            old_companies_to_realign = set()
            for partner_id, old_company_id in company_changes.items():
                partner = self.browse(partner_id)
                # Assign a fresh client_code from the new company's sequence
                partner.client_code = partner._get_next_sequence_client_code(
                    new_company_id
                )
                old_companies_to_realign.add(old_company_id)

            # Realign the sequence of each company the partners left,
            # so the gap they freed up can be reused later
            for old_company_id in old_companies_to_realign:
                self._realign_client_code_sequence(old_company_id)

        return res

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
        """Return the dedicated client code sequence for a company.
        If the company doesn't have one yet (e.g. newly assigned
        prefix_sequence not yet synced), try to create it on the fly.
        Falls back to the sequence with no company if nothing matches."""
        domain = [("code", "=", "res.partner.client.code")]
        domain += (
            [("company_id", "=", company_id)]
            if company_id
            else [("company_id", "=", False)]
        )
        sequence = self.env["ir.sequence"].sudo().search(domain, limit=1)

        if not sequence and company_id:
            company = self.env["res.company"].sudo().browse(company_id)
            if company.exists():
                # Lazily create the sequence if the company has a
                # prefix_sequence but no sequence yet (e.g. existing
                # company that was never backfilled).
                sequence = company._ensure_client_code_sequence()

        if not sequence and company_id:
            sequence = (
                self.env["ir.sequence"]
                .sudo()
                .search(
                    [
                        ("code", "=", "res.partner.client.code"),
                        ("company_id", "=", False),
                    ],
                    limit=1,
                )
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
    def _get_next_available_client_code(self, company_id=False, exclude_numbers=None):
        """Return the lowest unused client code number, ensuring global uniqueness."""
        sequence = self._get_sequence_for_company(company_id)
        if not sequence:
            return "/", None

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0
        
        # Récupérer TOUS les codes existants (pas seulement ceux de la société)
        existing_numbers = self._get_existing_client_code_numbers(prefix, company_id)
        
        # Ajouter aussi les codes d'autres sociétés avec le même préfixe
        all_partners = self.sudo().search([('client_code', 'like', f'{prefix}%')])
        for partner in all_partners:
            code = partner.client_code
            if code and code.startswith(prefix):
                num_part = code[len(prefix):]
                if num_part.isdigit():
                    existing_numbers.add(int(num_part))
        
        existing_numbers |= set(exclude_numbers or [])

        candidate = 1
        while candidate in existing_numbers:
            candidate += 1

        new_code = f"{prefix}{str(candidate).zfill(padding)}"

        if candidate >= sequence.number_next_actual:
            sequence.number_next = candidate + 1

        return new_code, candidate

    @api.model
    def _realign_client_code_sequence(self, company_id=False):
        """Reset the sequence pointer to just after the highest remaining
        client code, considering all companies for uniqueness."""
        sequence = self._get_sequence_for_company(company_id)
        if not sequence:
            return

        prefix = sequence.prefix or ""
        
        # Récupérer tous les numéros avec ce préfixe, toutes sociétés confondues
        all_numbers = set()
        partners = self.sudo().search([('client_code', 'like', f'{prefix}%')])
        for partner in partners:
            code = partner.client_code
            if code and code.startswith(prefix):
                num_part = code[len(prefix):]
                if num_part.isdigit():
                    all_numbers.add(int(num_part))
        
        max_number = max(all_numbers, default=0)

        if sequence.number_next_actual != max_number + 1:
            sequence.number_next = max_number + 1

    @api.constrains('client_code')
    def _check_client_code_unique(self):
        """Vérifie l'unicité du code client, en ignorant les codes temporaires."""
        for partner in self:
            if partner.client_code:
                # Ignorer les codes temporaires (utilisés pendant la fusion)
                if partner.client_code.startswith('__TMP__'):
                    continue
                    
                # Vérifier les doublons en excluant les codes temporaires
                existing = self.search([
                    ('client_code', '=', partner.client_code),
                    ('id', '!=', partner.id),
                    ('client_code', 'not like', '__TMP__%')  # Exclure les temporaires
                ], limit=1)
                
                if existing:
                    raise ValidationError(
                        _("Le code client '%s' est déjà utilisé par %s (ID: %s).") 
                        % (partner.client_code, existing.display_name, existing.id)
                    )

    # ----------------------------------------
    # Maintenance action
    # ----------------------------------------

    def action_assign_client_code(self):
        """Maintenance action: assign a client code to partners that don't
        have one yet (e.g. legacy data created before this module, or
        imported records). Fills the lowest available gap."""
        reserved_numbers_by_company = {}
        for partner in self:
            if not partner.client_code:
                company_id = partner.company_id.id
                reserved = reserved_numbers_by_company.setdefault(company_id, set())
                code, number = partner._get_next_available_client_code(
                    company_id, exclude_numbers=reserved
                )
                partner.client_code = code
                if number is not None:
                    reserved.add(number)

    # ----------------------------------------
    # View customization for Studio fields
    # ----------------------------------------

    @api.model
    def get_views(self, views, options=None):
        res = super().get_views(views, options=options)
        if "form" in res["views"]:
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
    def action_clear_all_client_codes(self):
        """Maintenance: clear client_code on ALL partners via raw SQL."""
        self.env.cr.execute("""
            UPDATE res_partner
            SET client_code = NULL
            WHERE client_code IS NOT NULL;
        """)
        self.env.cr.commit()

    @api.model
    def cron_backfill_client_codes(self):
        """Scheduled action: backfill client_code for all partners missing
        one, scoped per company, using raw SQL for performance on large
        datasets. Also realigns each company's sequence afterward.
        Uses res_company.prefix_sequence as the source of truth for
        each company's prefix instead of a hardcoded mapping."""

        # Step 0: make sure every company has a prefix_sequence set,
        # falling back to initials derived from the company name
        self.env.cr.execute("""
            UPDATE res_company
            SET prefix_sequence = UPPER(
                LEFT(regexp_replace(name, '\\s+.*', ''), 3)
            )
            WHERE prefix_sequence IS NULL OR prefix_sequence = '';
        """)

        # Step 1: backfill partners that belong to a company
        self.env.cr.execute("""
            WITH company_prefix AS (
                SELECT id AS company_id, prefix_sequence AS prefix
                FROM res_company
                WHERE prefix_sequence IS NOT NULL AND prefix_sequence != ''
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

        # Step 2: backfill partners with no company (fallback prefix "CL",
        # kept distinct since these partners have no company to derive
        # a prefix from)
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
                    cp.prefix_sequence AS prefix,
                    COALESCE(MAX(
                        CASE WHEN p.client_code ~ ('^' || cp.prefix_sequence || '[0-9]+$')
                            THEN substring(p.client_code FROM length(cp.prefix_sequence) + 1)::int
                        END
                    ), 0) AS max_num
                FROM res_company cp
                LEFT JOIN res_partner p ON p.company_id = cp.id
                WHERE cp.prefix_sequence IS NOT NULL AND cp.prefix_sequence != ''
                GROUP BY cp.id, cp.prefix_sequence
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

        # Step 5: ensure ir.sequence records exist for any company that
        # has a prefix_sequence but no sequence yet
        for company in self.env["res.company"].search(
            [("prefix_sequence", "!=", False)]
        ):
            company._ensure_client_code_sequence()
