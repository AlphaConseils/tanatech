/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PaymentForm } from "@payment/js/payment_form";

/**
 * MCB Payment Gateway — Odoo 18 PaymentForm integration.
 *
 * Odoo's _processRedirectFlow expects a <form> element in redirect_form_html.
 * MCB uses a Hosted Session inline form (no <form> tag).
 *
 * This patch intercepts the redirect flow for MCB and injects the rendered
 * MCB template (which contains the real session ID + PaymentSession.configure)
 * directly into the checkout page.
 *
 * Flow:
 *   1. Page loads → MCB inline form placeholder shown (empty session, no iFrames)
 *   2. User clicks "Confirmer la commande"
 *   3. Odoo creates transaction server-side + MCB session created
 *   4. _processRedirectFlow receives redirect_form_html with real session ID
 *   5. This patch injects the HTML + loads session.js + runs PaymentSession.configure
 *   6. MCB iFrames load — user enters card data
 *   7. User clicks "Pay now" inside the MCB form
 *   8. mcbSubmitPayment() calls /payment/mcb/pay → redirect to /payment/status
 */
patch(PaymentForm.prototype, {
    _processRedirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== "mcb") {
            return super._processRedirectFlow(...arguments);
        }

        const html = processingValues["redirect_form_html"];
        if (!html) {
            return;
        }

        // Build the new MCB form container from the server-rendered HTML.
        const wrapper = document.createElement("div");
        wrapper.innerHTML = html;

        // Remove anti-clickjack style before injecting into the page.
        const antiClickjack = wrapper.querySelector("#antiClickjack");
        if (antiClickjack) {
            antiClickjack.remove();
        }

        // Replace the inline placeholder (empty session) with the real form.
        const placeholder = document.querySelector(".o_payment_mcb_form");
        if (placeholder) {
            placeholder.replaceWith(wrapper);
        } else {
            const inlineContainer = document.querySelector(
                '[name="o_payment_inline_form"]'
            );
            if (inlineContainer) {
                inlineContainer.appendChild(wrapper);
            } else {
                document.body.appendChild(wrapper);
            }
        }

        // Separate external scripts (session.js) from inline config scripts.
        const externalScripts = Array.from(wrapper.querySelectorAll("script[src]"));
        const inlineScripts = Array.from(
            wrapper.querySelectorAll("script:not([src])")
        );

        const runInlineScripts = () => {
            inlineScripts.forEach((oldScript) => {
                const newScript = document.createElement("script");
                newScript.textContent = oldScript.textContent;
                document.head.appendChild(newScript);
            });
        };

        if (externalScripts.length > 0) {
            // Load external scripts (MCB session.js) first, then run inline scripts.
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
