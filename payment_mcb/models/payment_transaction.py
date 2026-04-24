# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    mcb_session_id = fields.Char(string='MCB Session ID', readonly=True)
    mcb_order_id = fields.Char(string='MCB Order ID', readonly=True)
    mcb_transaction_id = fields.Char(string='MCB Transaction ID', readonly=True)
    mcb_auth_code = fields.Char(string="Authorization Code", readonly=True)

    # ── Form Rendering ─────────────────────────────────────────────────────

    def _get_specific_rendering_values(self, processing_values):
        """
        Odoo 18: returns the values required by the inline QWeb template.
        Creates and initialises the MCB session server-side.
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'mcb':
            return res

        provider = self.provider_id

        # MCB IDs: replace '/' with '-' (MCB does not accept '/' in references)
        mcb_order_id = self.reference.replace('/', '-').replace(' ', '-')
        mcb_transaction_id = f"{mcb_order_id}-1"

        # Step 1: Create the session
        session_id = provider._mcb_create_session(
            order_id=mcb_order_id,
            amount=self.amount,
            currency_name=self.currency_id.name,
        )

        # Step 2: Update the session with amount and currency
        provider._mcb_update_session(
            session_id=session_id,
            amount=self.amount,
            currency_name=self.currency_id.name,
            order_reference=mcb_order_id,
        )

        # Persist MCB IDs on the Odoo transaction
        self.write({
            'mcb_session_id': session_id,
            'mcb_order_id': mcb_order_id,
            'mcb_transaction_id': mcb_transaction_id,
        })

        return {
            **res,
            'reference': self.reference,
            'session_id': session_id,
            'session_js_url': provider._mcb_get_session_js_url(),
            'merchant_id': provider.mcb_merchant_id,
            'order_id': mcb_order_id,
            'transaction_id': mcb_transaction_id,
            'amount': self.amount,
            'currency': self.currency_id.name,
            'return_url': provider._mcb_get_return_url(),
        }

    # ── MCB Response Processing ────────────────────────────────────────────

    def _process_notification_data(self, notification_data):
        """
        Odoo 18: processes MCB notification/webhook data
        and updates the transaction state.
        """
        super()._process_notification_data(notification_data)
        if self.provider_code != 'mcb':
            return

        result = notification_data.get('result', '')
        gateway_code = notification_data.get('response', {}).get('gatewayCode', '')
        auth_code = notification_data.get('response', {}).get('authorizationCode', '')

        _logger.info(
            "MCB notification tx=%s result=%s gateway_code=%s",
            self.reference, result, gateway_code,
        )

        if auth_code:
            self.mcb_auth_code = auth_code

        if result == 'SUCCESS' or gateway_code == 'APPROVED':
            self._set_done()
        elif result in ('PENDING', 'SUBMITTED'):
            self._set_pending()
        elif result in ('FAILURE', 'DECLINED', 'FAILED'):
            self._set_canceled(
                state_message=_("Payment declined (code: %s)") % gateway_code
            )
        else:
            _logger.warning("MCB: unknown status '%s' for transaction %s", result, self.reference)

    def _process_mcb_payment_response(self, response_data):
        """Processes the direct PAY API response."""
        if self.provider_code != 'mcb':
            return
        mcb_tx_id = response_data.get('transaction', {}).get('id', '')
        if mcb_tx_id:
            self.mcb_transaction_id = mcb_tx_id
        self._process_notification_data(response_data)

    @api.model
    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """
        Odoo 18: resolves the Odoo transaction from MCB notification data.
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'mcb' or len(tx) == 1:
            return tx

        mcb_order_ref = notification_data.get('order', {}).get('id', '')
        if mcb_order_ref:
            odoo_ref = mcb_order_ref.replace('-', '/')
            tx = self.search([('reference', '=', odoo_ref), ('provider_code', '=', 'mcb')])
            if not tx:
                tx = self.search([('mcb_order_id', '=', mcb_order_ref), ('provider_code', '=', 'mcb')])

        if not tx:
            raise ValidationError(
                _("MCB: No transaction found for reference %s") % mcb_order_ref
            )
        return tx
