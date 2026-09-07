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
      GET  /payment/mcb/return   → Return handler after Hosted Checkout
      POST /payment/mcb/webhook  → Asynchronous MCB notifications
    """

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
        """
        Return handler after MCB Hosted Checkout.

        MCB appends resultIndicator to the returnUrl we provided. We compare it
        to the stored mcb_success_indicator to determine the outcome:
          - match  → payment successful → _set_done()
          - no match → cancelled or declined → _set_canceled()
        """
        _logger.info("MCB Hosted Checkout return: %s", kwargs)

        order_id = kwargs.get('order_id', '')
        result_indicator = kwargs.get('resultIndicator', '')

        if not order_id:
            _logger.warning("MCB return: missing order_id in return URL")
            return request.redirect('/payment/status')

        tx = request.env['payment.transaction'].sudo().search([
            ('mcb_order_id', '=', order_id),
            ('provider_code', '=', 'mcb'),
        ], limit=1)

        if not tx:
            _logger.warning("MCB return: no transaction found for order_id=%s", order_id)
            return request.redirect('/payment/status')

        try:
            if result_indicator and tx.mcb_success_indicator == result_indicator:
                tx._set_done()
            else:
                tx._set_canceled(
                    state_message=_("Payment cancelled or declined by the customer.")
                )
        except Exception as e:
            _logger.error("MCB return: error processing transaction %s: %s", order_id, e)

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
