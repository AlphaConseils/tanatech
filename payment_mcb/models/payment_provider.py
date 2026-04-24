# -*- coding: utf-8 -*-
import logging
import requests
from requests.auth import HTTPBasicAuth

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

MCB_API_BASE_URL = 'https://mcb.gateway.mastercard.com/api/rest/version/72'
MCB_SESSION_JS_URL = 'https://mcb.gateway.mastercard.com/form/version/72/merchant/{merchant_id}/session.js'


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('mcb', 'MCB Payment Gateway')],
        ondelete={'mcb': 'set default'},
    )

    mcb_merchant_id = fields.Char(
        string='Merchant ID',
        required_if_provider='mcb',
        groups='base.group_system',
        help="Merchant identifier provided by MCB Payment Gateway.",
    )
    mcb_api_password = fields.Char(
        string='API Password',
        required_if_provider='mcb',
        groups='base.group_system',
        help="API password provided by MCB Payment Gateway.",
    )
    mcb_webhook_secret = fields.Char(
        string='Webhook Secret',
        groups='base.group_system',
        help="Secret used to validate MCB webhook notifications.",
    )
    mcb_3ds_enabled = fields.Boolean(
        string='Enable 3-D Secure',
        default=True,
    )

    # ── Odoo 18 Overrides ──────────────────────────────────────────────────

    # def _compute_feature_support_fields(self):
    #     super()._compute_feature_support_fields()
    #     self.filtered(lambda p: p.code == 'mcb').update({
    #         'support_tokenization': False,
    #         'support_manual_capture': None,
    #         'support_express_checkout': False,
    #         'support_refund': 'none',
    #     })

    def _get_supported_currencies(self):
        supported = super()._get_supported_currencies()
        if self.code == 'mcb':
            supported = supported.filtered(
                lambda c: c.name in ('MUR', 'USD', 'EUR', 'GBP', 'ZAR', 'AUD')
            )
        return supported

    def _get_default_payment_method_codes(self):
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'mcb':
            return default_codes
        return ['card']

    # ── MCB API Methods ────────────────────────────────────────────────────

    def _mcb_get_api_url(self, endpoint=''):
        return f"{MCB_API_BASE_URL}/merchant/{self.mcb_merchant_id}{endpoint}"

    def _mcb_get_auth(self):
        return HTTPBasicAuth(f'merchant.{self.mcb_merchant_id}', self.mcb_api_password)

    def _mcb_create_checkout_session(self, order_id, amount, currency_name, return_url):
        """Create a Mastercard Hosted Checkout session (full redirect, no iframes)."""
        url = self._mcb_get_api_url('/session')
        payload = {
            "apiOperation": "CREATE_CHECKOUT_SESSION",
            "order": {
                "id": order_id,
                "amount": float(amount),
                "currency": currency_name,
            },
            "interaction": {
                "operation": "PURCHASE",
                "returnUrl": return_url,
                "cancelUrl": f"{self.get_base_url()}/payment/status",
                "timeoutUrl": f"{self.get_base_url()}/payment/status",
            },
        }
        try:
            resp = requests.post(url, json=payload, auth=self._mcb_get_auth(), timeout=30)
            if not resp.ok:
                _logger.error(
                    "MCB create_checkout_session HTTP %s: %s", resp.status_code, resp.text
                )
                raise ValidationError(
                    _("MCB: Checkout session error %s: %s") % (resp.status_code, resp.text[:300])
                )
            data = resp.json()
            if data.get("result") != "SUCCESS":
                _logger.error("MCB create_checkout_session result: %s", data)
                raise ValidationError(
                    _("MCB: Checkout session creation failed: %s") % data.get("result")
                )
            session_id = data.get("session", {}).get("id")
            success_indicator = data.get("successIndicator", "")
            if not session_id:
                raise ValidationError(_("MCB: Unable to create checkout session."))
            _logger.info("MCB checkout session: %s (order %s)", session_id, order_id)
            return session_id, success_indicator
        except requests.exceptions.RequestException as e:
            _logger.error("MCB create_checkout_session: %s", e)
            raise ValidationError(_("MCB: Connection error: %s") % str(e))

    def _mcb_create_session(self, order_id, amount, currency_name):
        url = self._mcb_get_api_url('/session')
        try:
            resp = requests.post(
                url, json={"session": {"authenticationLimit": 25}},
                auth=self._mcb_get_auth(), timeout=30,
            )
            resp.raise_for_status()
            session_id = resp.json().get('session', {}).get('id')
            if not session_id:
                raise ValidationError(_("MCB: Unable to create session."))
            _logger.info("MCB session created: %s (order %s)", session_id, order_id)
            return session_id
        except requests.exceptions.RequestException as e:
            _logger.error("MCB create_session: %s", e)
            raise ValidationError(_("MCB: Connection error: %s") % str(e))

    def _mcb_update_session(self, session_id, amount, currency_name, order_reference):
        url = self._mcb_get_api_url(f'/session/{session_id}')
        payload = {
            "order": {
                "amount": float(amount),
                "currency": currency_name,
                "reference": order_reference,
                "description": f"Odoo Payment - {order_reference}",
            }
        }
        try:
            resp = requests.put(url, json=payload, auth=self._mcb_get_auth(), timeout=30)
            resp.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            _logger.error("MCB update_session: %s", e)
            raise ValidationError(_("MCB: Session update error: %s") % str(e))

    def _mcb_retrieve_session(self, session_id):
        url = self._mcb_get_api_url(f'/session/{session_id}')
        try:
            resp = requests.get(url, auth=self._mcb_get_auth(), timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            _logger.error("MCB retrieve_session: %s", e)
            return None

    def _mcb_pay(self, session_id, order_id, transaction_id, amount, currency_name, customer_email):
        url = self._mcb_get_api_url(f'/order/{order_id}/transaction/{transaction_id}')
        payload = {
            "apiOperation": "PAY",
            "session": {"id": session_id},
            "transaction": {"reference": transaction_id},
            "order": {
                "amount": float(amount),
                "currency": currency_name,
                "notificationUrl": self._mcb_get_webhook_url(),
            },
            "customer": {"email": customer_email},
        }
        if self.mcb_3ds_enabled:
            payload["authentication"] = {
                "channel": "PAYER_BROWSER",
                "redirectResponseUrl": self._mcb_get_return_url(),
            }
        try:
            resp = requests.put(url, json=payload, auth=self._mcb_get_auth(), timeout=60)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            _logger.error("MCB pay: %s", e)
            raise ValidationError(_("MCB: Erreur lors du paiement : %s") % str(e))

    def _mcb_get_session_js_url(self):
        return MCB_SESSION_JS_URL.format(merchant_id=self.mcb_merchant_id)

    def _mcb_get_webhook_url(self):
        return f"{self.get_base_url()}/payment/mcb/webhook"

    def _mcb_get_return_url(self):
        return f"{self.get_base_url()}/payment/mcb/return"
