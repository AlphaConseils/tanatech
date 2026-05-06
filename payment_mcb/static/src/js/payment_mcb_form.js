/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import PaymentForm from "@payment/js/payment_form";

patch(PaymentForm.prototype, {
    _processRedirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== "mcb") {
            return super._processRedirectFlow(...arguments);
        }
        // Extract checkout_url from the rendered form's action attribute
        const div = document.createElement("div");
        div.innerHTML = processingValues["redirect_form_html"] || "";
        const form = div.querySelector("form");
        const checkoutUrl = form && form.getAttribute("action");
        if (checkoutUrl) {
            window.location.href = checkoutUrl;
        }
    },
});
