/** @odoo-module */

import { renderToElement } from "@web/core/utils/render";
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

publicWidget.registry.CategoriesProduct = publicWidget.Widget.extend({
    selector: '.categories_section',

    start() {
        this._showSkeleton();
        this._observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                this._observer.disconnect();
                this._loadAndRender();
            }
        }, { rootMargin: '200px' });
        this._observer.observe(this.el);
        return this._super(...arguments);
    },

    destroy() {
        if (this._observer) this._observer.disconnect();
        this._super(...arguments);
    },

    _showSkeleton() {
        const card = () => `
            <div class="col-6 col-md-4 col-lg-3 mt-5">
                <div class="tana-skeleton-card rounded-item overflow-hidden">
                    <div class="tana-skeleton-pulse" style="width:100%;padding-top:100%;"></div>
                </div>
                <div class="tana-skeleton-pulse mt-3 mx-auto" style="height:14px;width:60%;border-radius:6px;"></div>
            </div>`;
        this.$target.html(`
            <div class="container-fluid px-md-5">
                <div class="brand-padding mb-4">
                    <div class="tana-skeleton-pulse" style="height:24px;width:180px;border-radius:6px;"></div>
                    <div class="tana-skeleton-pulse mt-2" style="height:14px;width:280px;border-radius:6px;"></div>
                </div>
                <div class="row g-4 brand-padding">
                    ${card()}${card()}${card()}${card()}
                </div>
            </div>
        `);
    },

    async _loadAndRender() {
        const result = await rpc('/get_product_categories', {});
        if (result) {
            this.$target.empty().html(renderToElement('tanatech_website.category_data', { result, _t }));
        }
    },
});
