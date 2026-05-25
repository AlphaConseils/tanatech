from odoo import api, models
from odoo.exceptions import AccessError
import logging

_logger = logging.getLogger(__name__)

# Contexte standard pour désactiver tous les effets de bord pendant la migration
_MIGRATION_CTX = {
    'tracking_disable':              True,   # pas de tracking des champs
    'mail_notrack':                  True,   # pas de chatter automatique
    'mail_create_nosubscribe':       True,   # pas d'abonnement auto à la création
    'mail_create_nolog':             True,   # pas de log "Document créé"
    'no_recompute':                  True,   # pas de recalcul des champs stockés
    'recompute':                     False,
}


class HrMigrationApi(models.AbstractModel):
    """
    Façade XML-RPC pour le script de migration RH.

    Toutes les méthodes sont préfixées par `migration_` et nécessitent
    d'être administrateur (group_system). Elles utilisent sudo() pour
    contourner les ACL métier et des contextes spéciaux pour supprimer
    les effets de bord (emails, tracking, abonnements automatiques).

    Appel depuis le script Python :
        tgt.execute('hr.migration.api', 'migration_create_record', 'hr.leave', vals, 'validate1')
    """

    _name        = 'hr.migration.api'
    _description = 'HR Migration API'

    # ─── ACCÈS ─────────────────────────────────────────────────────────────────

    def _check_access(self):
        if not self.env.user.has_group('base.group_system'):
            raise AccessError(
                "hr.migration.api : accès réservé aux administrateurs système."
            )

    def _migration_env(self):
        """
        Retourne un env avec le contexte de migration et toutes les sociétés
        dans allowed_company_ids, ce qui désactive les vérifications cross-company
        (_check_company) sur les champs many2one.
        """
        all_co_ids = self.env['res.company'].sudo().search([]).ids
        ctx = dict(self.env.context, **_MIGRATION_CTX, allowed_company_ids=all_co_ids)
        return self.env(context=ctx)

    # ─── CRÉATION GÉNÉRIQUE AVEC FORÇAGE DU STATE ──────────────────────────────

    @api.model
    def migration_create_record(self, model: str, vals: dict, state: str = None) -> int:
        """
        Crée un enregistrement dans `model` avec `vals`, puis force `state`
        si précisé (contourne les workflows Odoo).

        Retourne l'ID du nouvel enregistrement.
        """
        self._check_access()
        env = self._migration_env()
        model_env = env[model].sudo()
        if vals.get('company_id'):
            model_env = model_env.with_company(vals['company_id'])

        record = model_env.create(vals)
        _logger.info('migration_create_record: %s id=%s créé', model, record.id)

        if state:
            # _write contourne les contraintes ORM sur le state
            record.sudo()._write({'state': state})
            _logger.debug('migration_create_record: %s id=%s state forcé → %s', model, record.id, state)

        return record.id

    @api.model
    def migration_create_records_batch(self, model: str, vals_list: list, states: list = None) -> list:
        """
        Version batch de migration_create_record.
        `states` est une liste parallèle à `vals_list` (None = pas de forçage).

        Retourne la liste des IDs créés (dans le même ordre).
        """
        self._check_access()
        env = self._migration_env()
        company_id = vals_list[0].get('company_id') if vals_list else None
        model_env = env[model].sudo()
        if company_id:
            model_env = model_env.with_company(company_id)

        records = model_env.create(vals_list)
        new_ids = records.ids
        _logger.info('migration_create_records_batch: %s — %d enregistrements créés', model, len(new_ids))

        if states:
            for record, state in zip(records, states):
                if state:
                    record.sudo()._write({'state': state})

        return new_ids

    # ─── CHATTER : MESSAGES AVEC AUTEUR ET DATE D'ORIGINE ─────────────────────

    @api.model
    def migration_post_message(
        self,
        model:            str,
        res_id:           int,
        body:             str,
        author_partner_id: int  = None,
        date:             str  = None,
        subject:          str  = None,
        subtype_id:       int  = None,
    ) -> int:
        """
        Crée un mail.message en préservant l'auteur et la date d'origine.
        Contourne la restriction qui force author_id à l'utilisateur courant.

        Retourne l'ID du message créé.
        """
        self._check_access()

        vals = {
            'model':        model,
            'res_id':       res_id,
            'body':         body or '',
            'message_type': 'comment',
            'subtype_id':   subtype_id or self.env.ref('mail.mt_note').id,
        }
        if author_partner_id:
            vals['author_id'] = author_partner_id
        if date:
            vals['date'] = date
        if subject:
            vals['subject'] = subject

        msg = self.env['mail.message'].sudo().with_context(**_MIGRATION_CTX).create(vals)
        return msg.id

    @api.model
    def migration_post_messages_batch(self, messages: list) -> list:
        """
        Version batch : `messages` est une liste de dicts avec les clés :
          model, res_id, body, author_partner_id, date, subject, subtype_id
        Retourne la liste des IDs créés.
        """
        self._check_access()
        default_subtype = self.env.ref('mail.mt_note').id

        vals_list = []
        for m in messages:
            vals_list.append({
                'model':        m['model'],
                'res_id':       m['res_id'],
                'body':         m.get('body') or '',
                'message_type': 'comment',
                'subtype_id':   m.get('subtype_id') or default_subtype,
                'author_id':    m.get('author_partner_id') or self.env.user.partner_id.id,
                'date':         m.get('date') or False,
                'subject':      m.get('subject') or False,
            })

        msgs = self.env['mail.message'].sudo().with_context(**_MIGRATION_CTX).create(vals_list)
        _logger.info('migration_post_messages_batch: %d messages créés', len(msgs))
        return msgs.ids

    # ─── CHATTER : ABONNÉS ─────────────────────────────────────────────────────

    @api.model
    def migration_subscribe(
        self,
        model:       str,
        res_id:      int,
        partner_ids: list,
        subtype_ids: list = None,
    ) -> bool:
        """Abonne des partners à un enregistrement sans déclencher de notifications."""
        self._check_access()
        record = self.env[model].sudo().browse(res_id)
        record.with_context(**_MIGRATION_CTX).message_subscribe(
            partner_ids=partner_ids,
            subtype_ids=subtype_ids or [],
        )
        return True

    # ─── PIÈCES JOINTES ────────────────────────────────────────────────────────

    @api.model
    def migration_create_attachment(
        self,
        model:    str,
        res_id:   int,
        name:     str,
        datas:    str,           # base64 encodé
        mimetype: str = '',
        description: str = '',
    ) -> int:
        """Crée une pièce jointe liée à un enregistrement. Retourne l'ID."""
        self._check_access()
        att = self.env['ir.attachment'].sudo().with_context(**_MIGRATION_CTX).create({
            'name':        name,
            'datas':       datas,
            'mimetype':    mimetype,
            'description': description,
            'res_model':   model,
            'res_id':      res_id,
        })
        _logger.debug('migration_create_attachment: ir.attachment id=%s créé pour %s:%s', att.id, model, res_id)
        return att.id

    # ─── LETTRAGES COMPTABLES ──────────────────────────────────────────────────

    @api.model
    def migration_restore_reconcile(
        self,
        full_reconciles:    list,
        partial_reconciles: list,
    ) -> dict:
        """
        Restaure les lettrages comptables.

        full_reconciles    : liste de dicts {src_id, name}
        partial_reconciles : liste de dicts {debit_move_id, credit_move_id,
                              amount, debit_amount_currency, credit_amount_currency,
                              company_currency_id, debit_currency_id,
                              credit_currency_id, full_reconcile_src_id (optionnel)}

        Retourne {full_src_id: full_tgt_id} pour traçabilité.
        """
        self._check_access()
        env = self._migration_env()

        # 1. account.full.reconcile en premier (FK depuis partial)
        full_id_map = {}
        for frec in full_reconciles:
            src_id = frec.pop('src_id', None)
            try:
                new = env['account.full.reconcile'].sudo().create(frec)
                if src_id:
                    full_id_map[src_id] = new.id
            except Exception as exc:
                _logger.error('migration_restore_reconcile: full.reconcile erreur: %s', exc)

        # 2. account.partial.reconcile
        created_partial = 0
        for prec in partial_reconciles:
            full_src = prec.pop('full_reconcile_src_id', None)
            if full_src and full_src in full_id_map:
                prec['full_reconcile_id'] = full_id_map[full_src]
            try:
                env['account.partial.reconcile'].sudo().create(prec)
                created_partial += 1
            except Exception as exc:
                _logger.error('migration_restore_reconcile: partial.reconcile erreur: %s', exc)

        _logger.info(
            'migration_restore_reconcile: %d full + %d partial créés',
            len(full_id_map), created_partial,
        )
        return full_id_map

    # ─── UTILITAIRES ───────────────────────────────────────────────────────────

    @api.model
    def migration_get_writable_fields(self, model: str) -> dict:
        """
        Retourne les champs inscriptibles du modèle (store=True, pas readonly,
        pas one2many, pas système) avec leur type et relation.
        Utilisé par le script pour construire ses requêtes search_read.
        """
        self._check_access()
        fields_info = self.env[model].sudo().fields_get(
            attributes=['type', 'readonly', 'store', 'required', 'relation']
        )
        system = {
            'id', 'create_uid', 'write_uid', 'create_date', 'write_date',
            '__last_update', 'display_name',
            'message_ids', 'message_follower_ids', 'message_partner_ids',
            'activity_ids',
        }
        return {
            fname: {
                'type':     finfo.get('type'),
                'relation': finfo.get('relation', ''),
                'required': finfo.get('required', False),
            }
            for fname, finfo in fields_info.items()
            if fname not in system
            and not finfo.get('readonly', False)
            and finfo.get('store', True)
            and finfo.get('type') != 'one2many'
        }

    @api.model
    def migration_create_expense_sheet(self, vals: dict, expense_ids: list, state: str = None) -> int:
        """
        Crée un hr.expense.sheet en liant directement les dépenses via expense_line_ids.
        Le recompute est activé pour que employee_id et total_amount soient calculés
        depuis les dépenses — contrairement à _MIGRATION_CTX qui le désactive.
        """
        self._check_access()
        all_co_ids = self.env['res.company'].sudo().search([]).ids
        ctx = {
            'tracking_disable':        True,
            'mail_notrack':            True,
            'mail_create_nosubscribe': True,
            'mail_create_nolog':       True,
            'allowed_company_ids':     all_co_ids,
        }
        env = self.env(context=dict(self.env.context, **ctx))

        if expense_ids:
            vals['expense_line_ids'] = [(6, 0, expense_ids)]

        model_env = env['hr.expense.sheet'].sudo()
        if vals.get('company_id'):
            model_env = model_env.with_company(vals['company_id'])

        sheet = model_env.create(vals)
        if state:
            sheet.sudo()._write({'state': state})
        return sheet.id

    @api.model
    def migration_force_write(self, model: str, res_id: int, vals: dict) -> bool:
        """
        Force l'écriture de champs via _write() — contourne readonly et les
        contraintes ORM. Utile pour des champs comme sheet_id sur hr.expense.
        """
        self._check_access()
        self.env[model].sudo().browse(res_id).with_context(**_MIGRATION_CTX)._write(vals)
        return True

    @api.model
    def migration_ping(self) -> str:
        """Vérifie que le module est installé et l'utilisateur autorisé."""
        self._check_access()
        return f'ok — uid={self.env.uid} ({self.env.user.name})'
