/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { loadJS } from "@web/core/assets";
import paymentForm from '@payment/js/payment_form';

paymentForm.include({
    async _prepareInlineForm(providerId, providerCode, paymentOptionId, paymentMethodCode, flow) {
        if (providerCode !== 'mvola') {
            this._super(...arguments);
            return;
        }

        if (flow === 'token') {
            return;
        }

        this._setPaymentFlow('direct');
    },

    async _submitForm(ev) {
        ev.stopPropagation();
        ev.preventDefault();

        const checkedRadio = this.el.querySelector('input[name="o_payment_radio"]:checked');
        const providerCode = this.paymentContext.providerCode = this._getProviderCode(checkedRadio);

        if (providerCode !== "mvola") {
            return this._super(...arguments);
        }

        const msisdnInput = this.el.querySelector('#o_payment_mvola_num');
        const errorBox = this.el.querySelector('#o_mvola_error');
        const wrapper = this.el.querySelector('.o_mvola_input_wrapper');

        if (errorBox) errorBox.textContent = "";
        if (wrapper) wrapper.classList.remove("o_mvola_invalid");

        const customerMsisdn = msisdnInput?.value.trim() || "";

        if (!customerMsisdn) {
            const result = await this.rpc("/payment/customer_msisdn", {
                customer_msisdn: customerMsisdn,
            });

            if (result.error) {
                if (errorBox) {
                    errorBox.textContent = result.message;
                }
                if (wrapper) {
                    wrapper.classList.add("o_mvola_invalid");
                }
                return;
            }
        }

        return this._super(...arguments);
    },


    async _processDirectFlow(providerCode, paymentOptionId, paymentMethodCode, processingValues) {
        if (providerCode !== "mvola") {
            return this._super(...arguments);
        }

        const msisdnInput = document.querySelector('#o_payment_mvola_num');
        const errorBox = document.querySelector('#o_mvola_error');
        const wrapper = document.querySelector('.o_mvola_input_wrapper');

        if (errorBox) errorBox.textContent = "";
        if (wrapper) wrapper.classList.remove("o_mvola_invalid");

        const customerMsisdn = msisdnInput ? msisdnInput.value.trim() : "";

        const submitBtn = this.el.querySelector('button[type="submit"]');
        if (submitBtn) this._enableButton(submitBtn);

        try {
            const result = await this.rpc("/payment/mvola/init", {
                reference: processingValues.reference,
                customer_msisdn: customerMsisdn,
            });

            if (result.error) {
                if (errorBox) {
                    errorBox.textContent = result.message;
                }
                if (wrapper) {
                    wrapper.classList.add("o_mvola_invalid");
                }
                return;
            }

            window.location = "/payment/status";

        } catch (err) {
            if (errorBox) {
                errorBox.textContent =
                    err.data?.message || "Unexpected error occurred during MVola payment.";
            }
            if (wrapper) {
                wrapper.classList.add("o_mvola_invalid");
            }
        }
    }

});
