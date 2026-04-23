/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import PaymentForm from "@payment/js/payment_form";

/**
 * MCB Payment Gateway — Odoo 18 PaymentForm integration.
 *
 * Odoo generates redirect_form_html from the QWeb template referenced by
 * provider.redirect_form_view_id after the transaction is created server-side.
 *
 * This patch intercepts _processRedirectFlow for MCB (instead of submitting
 * a redirect <form>) and injects the rendered MCB hosted-session HTML into
 * the inline form container of the checkout page, then loads session.js.
 *
 * Flow:
 *   1. User clicks "Payer maintenant"
 *   2. Odoo creates transaction + MCB session (server-side)
 *   3. redirect_form_html is rendered with session_id / session_js_url
 *   4. _processRedirectFlow receives that HTML
 *   5. This patch injects the HTML into the payment option's inline container
 *   6. session.js loads → PaymentSession.configure() called → MCB iFrames appear
 *   7. User enters card data → clicks "Pay now" → mcbInitiatePayment()
 *   8. /payment/mcb/pay → redirect to /payment/status
 */
patch(PaymentForm.prototype, {
    _processRedirectFlow(providerCode, _paymentOptionId, _paymentMethodCode, processingValues) {
        if (providerCode !== "mcb") {
            return super._processRedirectFlow(...arguments);
        }

        const html = processingValues["redirect_form_html"];
        if (!html) {
            return;
        }

        // Build the wrapper from the server-rendered MCB template.
        const wrapper = document.createElement("div");
        wrapper.innerHTML = html;

        // Remove anti-clickjack style before attaching to the live document.
        const antiClickjack = wrapper.querySelector("#antiClickjack");
        if (antiClickjack) {
            antiClickjack.remove();
        }

        // Find the inline form container belonging to the selected MCB option.
        // We use the checked radio → its parent payment-option → its inline form div.
        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        let inlineContainer = null;
        if (checkedRadio) {
            const optionBlock = checkedRadio.closest('[name="o_payment_option"]');
            inlineContainer = optionBlock?.querySelector('[name="o_payment_inline_form"]');
        }

        if (inlineContainer) {
            inlineContainer.innerHTML = "";
            inlineContainer.appendChild(wrapper);
            inlineContainer.classList.remove("d-none");
        } else {
            // Fallback: append directly to body (should not happen in normal flow).
            document.body.appendChild(wrapper);
        }

        // Hide Odoo's submit button and lift the UI block so MCB iFrames are usable.
        this._hideInputs();
        this.call("ui", "unblock");

        // Separate external scripts (session.js) from inline configuration scripts.
        const externalScripts = Array.from(wrapper.querySelectorAll("script[src]"));
        const inlineScripts = Array.from(wrapper.querySelectorAll("script:not([src])"));

        const runInlineScripts = () => {
            inlineScripts.forEach((oldScript) => {
                const newScript = document.createElement("script");
                newScript.textContent = oldScript.textContent;
                document.head.appendChild(newScript);
            });
        };

        if (externalScripts.length > 0) {
            // Load MCB session.js first, then execute the inline PaymentSession.configure().
            let loadedCount = 0;
            externalScripts.forEach((oldScript) => {
                const newScript = document.createElement("script");
                newScript.src = oldScript.src;
                newScript.onload = () => {
                    loadedCount++;
                    if (loadedCount === externalScripts.length) {
                        runInlineScripts();
                    }
                };
                newScript.onerror = () => {
                    console.error("MCB: Failed to load session.js from", newScript.src);
                };
                document.head.appendChild(newScript);
            });
        } else {
            runInlineScripts();
        }
    },
});
