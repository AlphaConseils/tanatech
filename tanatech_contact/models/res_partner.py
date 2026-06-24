# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from lxml import etree


class ResPartner(models.Model):
    _inherit = "res.partner"

    # New fields
    client_code = fields.Char(
        string="Code Client", 
        copy=False, 
        readonly=True,
        index=True
    )

    # Re-declare Studio fields to ensure they exist and can be safely validated
    x_studio_nif_1 = fields.Char(string="NIF")
    x_studio_char_field_d3loF = fields.Char(string="STAT")

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
                    ('client_code', 'not like', '__TMP__%')
                ], limit=1)
                
                if existing:
                    raise ValidationError(
                        _("Le code client '%s' est déjà utilisé par %s (ID: %s).") 
                        % (partner.client_code, existing.display_name, existing.id)
                    )

    @api.onchange("company_id")
    def _onchange_company_id_client_code(self):
        """Preview the client_code that will be assigned once the record
        is saved, based on the newly selected company's sequence."""
        if not self.company_id:
            return
        sequence = self._get_sequence_for_company(self.company_id.id)
        if not sequence:
            return

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0
        
        # Chercher le prochain numéro disponible
        existing_numbers = self._get_all_existing_client_code_numbers(prefix)
        candidate = sequence.number_next_actual
        
        while candidate in existing_numbers:
            candidate += 1
            
        self.client_code = f"{prefix}{str(candidate).zfill(padding)}"

    @api.model
    def _get_next_sequence_client_code(self, company_id=False):
        """Return the next available client code for the given company's sequence,
        ensuring global uniqueness."""
        sequence = self._get_sequence_for_company(company_id)
        if not sequence:
            return "/"

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0
        candidate = sequence.number_next_actual

        # Récupérer tous les codes existants avec ce préfixe
        existing_numbers = self._get_all_existing_client_code_numbers(prefix)

        # Chercher un code unique (maximum 1000 tentatives pour éviter boucle infinie)
        max_attempts = 1000
        attempt = 0
        while attempt < max_attempts:
            new_code = f"{prefix}{str(candidate).zfill(padding)}"
            
            # Vérifier si ce code existe déjà dans la base
            existing = self.sudo().search([('client_code', '=', new_code)], limit=1)
            if not existing:
                sequence.number_next = candidate + 1
                return new_code
            candidate += 1
            attempt += 1
        
        raise ValidationError(
            _("Impossible de générer un code client unique après %s tentatives. "
              "Veuillez vérifier la séquence pour le préfixe '%s'.") 
            % (max_attempts, prefix)
        )

    @api.model_create_multi
    def create(self, vals_list):
        # Track codes assigned within this same create() call
        reserved_codes = set()

        for vals in vals_list:
            if not vals.get("client_code"):
                company_id = vals.get("company_id")
                code = self._get_unique_client_code(company_id, reserved_codes)
                vals["client_code"] = code
                reserved_codes.add(code)
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
                # Assign a fresh unique client_code from the new company's sequence
                new_code = self._get_unique_client_code(new_company_id)
                partner.with_context(skip_client_code_company_sync=True).write({
                    'client_code': new_code
                })
                old_companies_to_realign.add(old_company_id)

            # Realign sequences
            for old_company_id in old_companies_to_realign:
                self._realign_client_code_sequence(old_company_id)
            if new_company_id:
                self._realign_client_code_sequence(new_company_id)

        return res

    @api.model
    def _get_unique_client_code(self, company_id=False, reserved_codes=None):
        """Generate a unique client code that doesn't exist in DB or reserved list."""
        sequence = self._get_sequence_for_company(company_id)
        if not sequence:
            return "/"

        prefix = sequence.prefix or ""
        padding = sequence.padding or 0
        
        # Récupérer tous les codes existants
        existing_numbers = self._get_all_existing_client_code_numbers(prefix)
        
        # Ajouter les codes réservés dans cette transaction
        if reserved_codes:
            for code in reserved_codes:
                if code.startswith(prefix):
                    num_part = code[len(prefix):]
                    if num_part.isdigit():
                        try:
                            number = int(num_part)  # Utiliser int() explicitement
                            existing_numbers.add(number)
                        except (ValueError, TypeError):
                            pass
        
        # Commencer par le prochain numéro de séquence
        candidate = sequence.number_next_actual
        
        # Chercher le premier numéro disponible
        while candidate in existing_numbers:
            candidate += 1
        
        new_code = f"{prefix}{str(candidate).zfill(padding)}"
        
        # Mettre à jour la séquence si nécessaire
        if candidate >= sequence.number_next_actual:
            sequence.number_next = candidate + 1
        
        return new_code

    @api.model
    def _get_all_existing_client_code_numbers(self, prefix):
        """Récupère tous les numéros existants pour un préfixe donné, toutes sociétés confondues."""
        all_numbers = set()
        partners = self.sudo().search([('client_code', 'like', f'{prefix}%')])
        for partner in partners:
            code = partner.client_code
            if code and code.startswith(prefix):
                num_part = code[len(prefix):]
                if num_part.isdigit():
                    try:
                        # Utiliser la fonction builtins.int explicitement
                        import builtins
                        number = builtins.int(num_part)
                        all_numbers.add(number)
                    except (ValueError, TypeError):
                        pass
        return all_numbers

    @api.model
    def _get_existing_client_code_numbers(self, prefix, company_id=False):
        """Récupère les numéros existants pour un préfixe et une société."""
        domain = [('client_code', 'like', f'{prefix}%')]
        if company_id:
            domain.append(('company_id', '=', company_id))
        else:
            domain.append(('company_id', '=', False))
        
        partners = self.sudo().search(domain)
        numbers = set()
        for partner in partners:
            code = partner.client_code
            if code and code.startswith(prefix):
                num_part = code[len(prefix):]
                if num_part.isdigit():
                    try:
                        # Utiliser la fonction builtins.int explicitement
                        import builtins
                        number = builtins.int(num_part)
                        numbers.add(number)
                    except (ValueError, TypeError):
                        pass
        return numbers

    @api.model
    def _realign_client_code_sequence(self, company_id=False):
        """Reset the sequence pointer considering all companies for uniqueness."""
        sequence = self._get_sequence_for_company(company_id)
        if not sequence:
            return

        prefix = sequence.prefix or ""
        
        # Récupérer tous les numéros avec ce préfixe, toutes sociétés confondues
        all_numbers = self._get_all_existing_client_code_numbers(prefix)
        
        max_number = max(all_numbers, default=0)

        if sequence.number_next_actual <= max_number:
            sequence.number_next = max_number + 1

    # ... Reste des méthodes inchangées