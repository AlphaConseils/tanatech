# -*- coding: utf-8 -*-

import logging
import uuid
import re
import json
import time
import unicodedata
import requests

from odoo import http, _
from odoo.http import request
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing

_logger = logging.getLogger(__name__)


def clean_text(text):
    """Strip accents and non-ASCII characters from a string."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9 ]+", "", text)
    return text


class MVolaController(http.Controller):

    @http.route("/payment/customer_msisdn", type="json", auth="public", csrf=False)
    def customer_msisdn_check(self, customer_msisdn=None):
        if not customer_msisdn:
            return {"error": True, "message": _("Please enter your MVola phone number.")}
        return {"error": False}

    @http.route("/payment/mvola/init", type="json", auth="public", csrf=False)
    def mvola_init(self, reference=None, customer_msisdn=None):
        _logger.info("MVola INIT: reference=%s, msisdn=%s", reference, customer_msisdn)

        if not reference:
            return {"error": True, "message": _("Missing transaction reference.")}

        tx = (
            request.env["payment.transaction"]
            .sudo()
            .search([("reference", "=", reference)], limit=1)
        )
        if not tx:
            return {"error": True, "message": f"No transaction found for reference {reference}"}

        provider = tx.provider_id
        if provider.code != "mvola":
            return {"error": True, "message": _("Invalid payment provider.")}

        if not customer_msisdn:
            return {"error": True, "message": _("Please enter your MVola phone number.")}

        if (
            len(customer_msisdn) != 10
            or not customer_msisdn.isdigit()
            or not re.match(r"^0(34|38)[0-9]{7}$", customer_msisdn)
        ):
            return {
                "error": True,
                "message": _("Invalid MVola phone number (format: 034XXXXXXX or 038XXXXXXX)."),
            }

        merchant_msisdn = provider.mvola_phone
        mvola_url = provider.mvola_url

        if not merchant_msisdn:
            return {"error": True, "message": _("MVola merchant phone number is not configured.")}
        if not mvola_url:
            return {"error": True, "message": _("MVola base URL not configured.")}

        try:
            token = provider.sudo()._generate_mvola_access_token()
        except Exception as e:
            _logger.error("MVola token error: %s", e)
            return {"error": True, "message": _("Unable to generate MVola access token.")}

        msisdn_formatted = "+261" + customer_msisdn[1:]
        merchant_formatted = "+261" + merchant_msisdn[1:]
        partner_name = clean_text(tx.company_id.name or "")

        transaction_ref = str(uuid.uuid4())
        header = {
            "Version": "1.0",
            "X-CorrelationID": transaction_ref,
            "UserAccountIdentifier": f"msisdn;{msisdn_formatted}",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "UserLanguage": "MG",
            "partnerName": partner_name,
            "Cache-Control": "no-cache",
        }
        data = {
            "amount": str(int(tx.amount)),
            "currency": "Ar",
            "descriptionText": f"Payment {tx.reference}",
            "requestingOrganisationTransactionReference": transaction_ref.replace("-", ""),
            "requestDate": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "originalTransactionReference": transaction_ref.replace("-", ""),
            "debitParty": [{"key": "msisdn", "value": msisdn_formatted}],
            "creditParty": [{"key": "msisdn", "value": merchant_formatted}],
            "metadata": [
                {"key": "partnerName", "value": partner_name},
                {"key": "fc", "value": "USD"},
                {"key": "amountFc", "value": "1"},
            ],
        }

        url = f"{mvola_url}/mvola/mm/transactions/type/merchantpay/1.0.0/"
        try:
            response = requests.post(url=url, headers=header, data=json.dumps(data), timeout=30)
            _logger.info("MVola API Response (status=%s): %s", response.status_code, response.text)
        except Exception as e:
            _logger.error("MVola API error: %s", e)
            return {"error": True, "message": _("Unable to contact MVola API.")}

        try:
            json_resp = response.json()
        except Exception:
            json_resp = {"raw": response.text}

        if not (200 <= response.status_code < 300):
            return {
                "error": True,
                "message": _("An error occurred during the MVola payment."),
                "details": json_resp,
            }

        if "fault" in json_resp:
            fault = json_resp["fault"]
            return {
                "error": True,
                "message": _("MVola Error: ") + fault.get("message", "Unknown error."),
                "details": fault,
            }

        if json_resp.get("status") == "pending":
            mvola_method = request.env.ref("payment_mvola.payment_method_mvola").id
            token_id = (
                request.env["payment.token"]
                .sudo()
                .create({
                    "provider_id": provider.id,
                    "payment_method_id": mvola_method,
                    "partner_id": tx.partner_id.id,
                    "payment_details": json_resp.get("serverCorrelationId", "mvola"),
                    "partner_phone": customer_msisdn,
                    "correlation_id": transaction_ref,
                    "provider_ref": json_resp.get("serverCorrelationId", transaction_ref),
                    "active": True,
                })
            )
            tx.sudo().write({
                "token_id": token_id.id,
                "provider_reference": json_resp.get("transactionReference"),
                "state_message": str(json_resp),
            })
        else:
            tx.sudo().write({
                "provider_reference": json_resp.get("transactionReference"),
                "state_message": str(json_resp),
            })

        return {"error": False, "mvola_response": json_resp}


class MVolaPaymentPostProcessing(PaymentPostProcessing):

    def _get_mvola_transaction_status(self, tx):
        """Poll MVola API for the current status of a transaction.

        :param payment.transaction tx: The transaction to check
        :return: The MVola API response dict
        :rtype: dict
        """
        provider = tx.provider_id
        try:
            token = provider.sudo()._generate_mvola_access_token()
        except Exception as e:
            _logger.error("MVola token refresh failed: %s", e)
            return {}

        merchant_msisdn = provider.mvola_phone
        merchant_formatted = "+261" + merchant_msisdn[1:]
        correlation_id = tx.token_id.provider_ref or ""

        header = {
            "Version": "1.0",
            "X-CorrelationID": correlation_id,
            "UserLanguage": "MG",
            "UserAccountIdentifier": f"msisdn;{merchant_formatted}",
            "partnerName": clean_text(tx.company_id.name or ""),
            "Authorization": f"Bearer {token}",
            "Cache-Control": "no-cache",
        }

        url = (
            f"{provider.mvola_url}/mvola/mm/transactions/type/merchantpay/1.0.0/status/"
            f"{correlation_id}"
        )
        try:
            response = requests.get(url, headers=header, timeout=30)
            return response.json()
        except Exception as e:
            _logger.warning("MVola status poll error: %s", e)
            return {}

    @http.route()
    def poll_status(self, **_kwargs):
        monitored_tx = self._get_monitored_transaction()
        if monitored_tx and monitored_tx.provider_id.code == "mvola":
            if monitored_tx.token_id and monitored_tx.state in ("draft", "pending"):
                transaction_status = self._get_mvola_transaction_status(monitored_tx)
                status_code = transaction_status.get("status")

                if status_code == "completed":
                    monitored_tx.sudo()._set_done()
                    monitored_tx.token_id.sudo().write({"active": False})
                elif status_code == "failed":
                    monitored_tx.sudo()._set_error(
                        _("An error occurred during the MVola payment. Please retry.")
                    )

        return super().poll_status(**_kwargs)
