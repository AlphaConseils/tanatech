# -*- coding: utf-8 -*-

import base64
import logging
import requests
from odoo import _, fields, models, api, exceptions

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("mvola", "Mvola")], ondelete={"mvola": "set default"}
    )
    mvola_consumer_key = fields.Char(string="Consumer Key")
    mvola_consumer_secret = fields.Char(string="Consumer Secret")
    mvola_status = fields.Selection(
        [("sandbox", "SANDBOX"), ("production", "PRODUCTION")], string="Environment"
    )
    mvola_url = fields.Char(string="API URL", compute="_compute_gateway_url", store=False)
    mvola_token = fields.Char(string="Access Token")
    mvola_phone = fields.Char(string="Merchant Phone")

    @api.depends("mvola_status")
    def _compute_gateway_url(self):
        for record in self:
            if record.mvola_status:
                record.mvola_url = (
                    "https://api.mvola.mg"
                    if record.mvola_status == "production"
                    else "https://devapi.mvola.mg"
                )
            else:
                record.mvola_url = False

    def _generate_mvola_access_token(self):
        """Generate an OAuth2 access token from MVola API.

        :return: The access token string
        :rtype: str
        :raise: exceptions.UserError if the token generation fails
        """
        url = f"{self.mvola_url}/token"
        keys = f"{self.mvola_consumer_key}:{self.mvola_consumer_secret}"
        encoded = base64.b64encode(keys.encode("ascii")).decode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cache-Control": "no-cache",
            "Authorization": f"Basic {encoded}",
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "EXT_INT_MVOLA_SCOPE",
        }
        try:
            req = requests.post(url, headers=headers, data=data, timeout=30)
            req.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error("MVola token generation failed: %s", e)
            raise exceptions.UserError(
                _("Unable to reach MVola API. Check your internet connection.")
            )
        response_json = req.json()
        if "error" in response_json:
            raise exceptions.UserError(
                _("Failed to generate token. Check Consumer Key and Consumer Secret.")
            )
        return response_json["access_token"]

    def generate_token(self):
        """Refresh the MVola access token for all enabled MVola providers.

        Called by the cron job every minute.
        """
        mvola_providers = self.search([("code", "=", "mvola"), ("state", "!=", "disabled")])
        for provider in mvola_providers:
            if provider.mvola_consumer_key and provider.mvola_consumer_secret and provider.mvola_url:
                try:
                    token = provider._generate_mvola_access_token()
                    provider.sudo().mvola_token = token
                except exceptions.UserError as e:
                    _logger.warning("MVola token refresh failed for provider %s: %s", provider.id, e)

    def button_generate_token(self):
        """Manually refresh the MVola access token from the provider form."""
        self.ensure_one()
        token = self._generate_mvola_access_token()
        self.mvola_token = token
