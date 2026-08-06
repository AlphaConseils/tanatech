# -*- coding: utf-8 -*-
import logging

from odoo.exceptions import ValidationError
from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)


class WebsiteSaleManualPayment(WebsiteSale):

    @route(
        '/shop/payment/manual',
        type='http',
        auth='public',
        methods=['POST'],
        website=True,
        sitemap=False,
    )
    def shop_payment_manual(self, **post):
        """ Validate the checkout without any online payment.

        Used as long as no payment provider is available: the cart is turned
        into a quotation, the sales team receives an activity to contact the
        customer and the customer is redirected to their portal.
        """
        order_sudo = request.website.sale_get_order()

        if redirection := self._check_cart_and_addresses(order_sudo):
            return redirection

        if redirection := self._check_shipping_method(order_sudo):
            return redirection

        if not order_sudo.company_id.website_manual_payment_enabled:
            return request.redirect('/shop/payment')

        try:
            order_sudo._check_cart_is_ready_to_be_paid()
        except ValidationError:
            _logger.info(
                "tanatech_website_sale: cart %s is not ready to be validated,"
                " back to the payment step.",
                order_sudo.id,
            )
            return request.redirect('/shop/payment')

        order_sudo._process_website_manual_payment_request()

        # Release the cart so that the customer starts a new one on their next visit.
        request.session['sale_last_order_id'] = order_sudo.id
        request.website.sale_reset()

        return request.redirect(order_sudo.get_portal_url())
