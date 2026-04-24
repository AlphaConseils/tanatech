/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import PaymentForm from "@payment/js/payment_form";

/**
 * MCB Payment Gateway — Odoo 18 PaymentForm integration.
 *
 * Root problem this patch solves:
 *   Calling _hideInputs() / ui.unblock() triggers an OWL re-render that
 *   resets inlineContainer to its original (empty) state, wiping any MCB
 *   HTML we injected before that call.
 *
 * Fix: unblock UI first (so OWL re-renders synchronously via microtasks),
 * then defer the actual DOM injection into a setTimeout(0) callback which
 * runs after all pending microtasks — i.e. after OWL is done rendering.
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

        // 1. Unblock UI / hide Odoo's submit button FIRST so that any OWL
        //    re-render they trigger completes before we touch the DOM.
        this._hideInputs();
        this.call("ui", "unblock");

        // 2. Capture el reference before the async gap (remains valid across renders).
        const componentEl = this.el;

        // 3. Defer injection until after OWL's microtask-based render cycle.
        setTimeout(() => {
            const wrapper = document.createElement("div");
            wrapper.innerHTML = html;

            // Remove anti-clickjack style before attaching to the live document.
            const antiClickjackStyle = wrapper.querySelector("#antiClickjack");
            if (antiClickjackStyle) {
                antiClickjackStyle.remove();
            }

            // Find the inline container of the selected MCB payment option.
            const checkedRadio = componentEl
                ? componentEl.querySelector('input[name="o_payment_radio"]:checked')
                : document.querySelector('input[name="o_payment_radio"]:checked');

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
                // Fallback: should not happen in normal flow.
                console.warn("[MCB] inline container not found, appending to body");
                document.body.appendChild(wrapper);
            }

            // Load session.js first, then run inline PaymentSession.configure().
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
                        console.error("[MCB] Failed to load session.js from", newScript.src);
                    };
                    document.head.appendChild(newScript);
                });
            } else {
                runInlineScripts();
            }
        }, 0);
    },
});
