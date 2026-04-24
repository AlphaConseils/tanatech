# -*- coding: utf-8 -*-
import hashlib
import hmac
import json
import logging

from werkzeug.exceptions import Forbidden

from odoo import http, _
from odoo.http import request
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class MCBPaymentController(http.Controller):
    """
    MCB Payment Gateway controller — Odoo 18.

    Routes:
      POST /payment/mcb/pay      → Triggers the server-to-server PAY operation
      GET  /payment/mcb/return   → Return handler after 3-D Secure
      POST /payment/mcb/webhook  → Asynchronous MCB notifications
    """

    # ── /payment/mcb/pay ──────────────────────────────────────────────────

    @http.route(
        '/payment/mcb/pay',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def mcb_pay(self, session_id=None, reference=None, **_kwargs):
        """
        Receives the session_id updated by PaymentSession.updateSessionFromForm()
        and triggers the server-side MCB PAY operation.
        """
        if not session_id or not reference:
            return {'success': False, 'error': _("Missing parameters.")}

        tx = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'mcb'),
            ('state', 'in', ('draft', 'pending')),
        ], limit=1)

        if not tx:
            _logger.warning("MCB /pay: transaction not found (ref=%s)", reference)
            return {'success': False, 'error': _("Transaction not found.")}

        if tx.mcb_session_id != session_id:
            _logger.warning("MCB /pay: session_id mismatch tx=%s", reference)
            return {'success': False, 'error': _("Invalid session.")}

        provider = tx.provider_id

        try:
            # Verify session before payment (MCB best practice)
            session_data = provider._mcb_retrieve_session(session_id)
            if not session_data:
                return {'success': False, 'error': _("Unable to verify session.")}

            # Execute PAY operation
            response = provider._mcb_pay(
                session_id=session_id,
                order_id=tx.mcb_order_id,
                transaction_id=tx.mcb_transaction_id,
                amount=tx.amount,
                currency_name=tx.currency_id.name,
                customer_email=tx.partner_email or '',
            )

            tx._process_mcb_payment_response(response)

            result      = response.get('result', '')
            gateway_code = response.get('response', {}).get('gatewayCode', '')

            if result == 'SUCCESS' or gateway_code == 'APPROVED':
                return {'success': True, 'redirect_url': '/payment/status'}
            elif result == 'PENDING':
                return {'success': True, 'redirect_url': '/payment/status', 'pending': True}
            else:
                error_msg = response.get('error', {}).get('explanation', _("Payment declined"))
                return {'success': False, 'error': error_msg}

        except ValidationError as e:
            _logger.error("MCB /pay ValidationError: %s", e)
            return {'success': False, 'error': str(e)}
        except Exception:
            _logger.exception("MCB /pay unexpected error")
            return {'success': False, 'error': _("Unexpected error. Please try again.")}

    # ── /payment/mcb/return ───────────────────────────────────────────────

    @http.route(
        '/payment/mcb/return',
        type='http',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
        save_session=False,
    )
    def mcb_return(self, **kwargs):
        """Return page after MCB Hosted Checkout."""
        order_id = kwargs.get('order_id', '')
        result_indicator = kwargs.get('resultIndicator', '')

        _logger.info(
            "MCB Hosted Checkout return: order_id=%s result_indicator=%s",
            order_id, result_indicator,
        )

        if order_id:
            tx = request.env['payment.transaction'].sudo().search([
                ('mcb_order_id', '=', order_id),
                ('provider_code', '=', 'mcb'),
            ], limit=1)
            if tx:
                try:
                    if result_indicator and result_indicator == tx.mcb_success_indicator:
                        tx._set_done()
                        _logger.info("MCB: payment confirmed for tx %s", tx.reference)
                    else:
                        # Cancelled or failed — retrieve session for full status
                        session_data = tx.provider_id._mcb_retrieve_session(
                            tx.mcb_session_id
                        )
                        if session_data:
                            tx._process_notification_data(session_data)
                        else:
                            tx._set_canceled(state_message=_("Payment cancelled."))
                except Exception as e:
                    _logger.error("MCB return processing error: %s", e)

        return request.redirect('/payment/status')

    # ── /payment/mcb/webhook ──────────────────────────────────────────────

    @http.route(
        '/payment/mcb/webhook',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False,
        save_session=False,
    )
    def mcb_webhook(self, **_kwargs):
        """Receives and processes asynchronous MCB notifications."""
        try:
            payload_bytes = request.httprequest.get_data()
            notification_data = json.loads(payload_bytes)
        except Exception as e:
            _logger.error("MCB webhook: invalid payload: %s", e)
            return http.Response(status=400)

        _logger.info("MCB webhook: %s", notification_data)

        provider = request.env['payment.provider'].sudo().search([
            ('code', '=', 'mcb'),
            ('state', 'in', ('enabled', 'test')),
        ], limit=1)

        if not provider:
            _logger.error("MCB webhook: no active provider found")
            return http.Response(status=404)

        # Verify HMAC signature if secret is configured
        if provider.mcb_webhook_secret:
            sig = request.httprequest.headers.get('X-Notification-Signature', '')
            if not self._check_signature(payload_bytes, sig, provider.mcb_webhook_secret):
                _logger.warning("MCB webhook: invalid signature")
                raise Forbidden()

        try:
            tx = request.env['payment.transaction'].sudo()._get_tx_from_notification_data(
                'mcb', notification_data
            )
            tx._process_notification_data(notification_data)
        except ValidationError as e:
            _logger.error("MCB webhook processing: %s", e)
            return http.Response(status=400)

        return http.Response(status=200)

    # ── Utilities ─────────────────────────────────────────────────────────

    @staticmethod
    def _check_signature(payload_bytes, received, secret):
        if not received:
            return False
        expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, received)
