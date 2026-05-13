/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { renderToElement } from "@web/core/utils/render";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.PromotionalProduct = publicWidget.Widget.extend({
    selector: '.promotions_section',

    start() {
        if (!this.el.id) {
            this.el.id = 'promotions';
        }
        this._showSkeleton();
        this._observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                this._observer.disconnect();
                this._loadAndRender();
            }
        }, { rootMargin: '200px' });
        this._observer.observe(this.el);
        this._handleAnchor();
        this._onHashChange = this._handleAnchor.bind(this);
        window.addEventListener('hashchange', this._onHashChange);
        return this._super(...arguments);
    },

    _handleAnchor() {
        if (window.location.hash === '#' + this.el.id) {
            this.el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    },

    destroy() {
        if (this._observer) this._observer.disconnect();
        if (this._onHashChange) window.removeEventListener('hashchange', this._onHashChange);
        this._super(...arguments);
    },

    _showSkeleton() {
        const card = () => `
            <div class="px-2" style="min-width:220px;flex:1">
                <div class="tana-skeleton-card rounded-item p-3">
                    <div class="tana-skeleton-pulse" style="width:100%;padding-top:100%;border-radius:8px;"></div>
                    <div class="tana-skeleton-pulse mt-3" style="height:14px;width:70%;border-radius:6px;"></div>
                    <div class="tana-skeleton-pulse mt-2" style="height:12px;width:40%;border-radius:6px;"></div>
                    <div class="tana-skeleton-pulse mt-3" style="height:36px;border-radius:8px;"></div>
                </div>
            </div>`;
        this.$target.html(`
            <div class="brand-padding py-3">
                <div class="tana-skeleton-pulse mb-3" style="height:20px;width:220px;border-radius:6px;"></div>
                <div class="d-flex gap-3 overflow-hidden">
                    ${card()}${card()}${card()}${card()}
                </div>
            </div>
        `);
    },

    async _loadAndRender() {
        const result = await rpc('/get_promotional_products', {});
        if (!result) return;
        const labels = result.labels;
        this.$target.html(renderToElement('tanatech_website.promotional_snippet', { result, labels }));
        this._initSwiper();
        this._bindCartEvents();
    },

    _initSwiper() {
        setTimeout(() => {
            new Swiper(this.$target.find('.promotions-carousel')[0], {
                slidesPerView: 4,
                grid: { rows: 2, fill: "row" },
                spaceBetween: 15,
                navigation: { nextEl: this.$target.find('.promo-nav-next')[0], prevEl: this.$target.find('.promo-nav-prev')[0] },
                pagination: { el: this.$target.find('.promo-pagination')[0], clickable: true },
                speed: 900,
                autoplay: { delay: 5000, disableOnInteraction: false, pauseOnMouseEnter: true },
                watchOverflow: true,
                breakpoints: {
                    0:   { slidesPerView: 1, grid: { rows: 2 } },
                    576: { slidesPerView: 2, grid: { rows: 2 } },
                    768: { slidesPerView: 3, grid: { rows: 2 } },
                    992: { slidesPerView: 4, grid: { rows: 2 } },
                },
            });
        }, 100);
    },

    _showCartToast(productName, qty) {
        let $container = $('#tana-toast-container');
        if (!$container.length) {
            $container = $('<div id="tana-toast-container">');
            $container.css({ position: 'fixed', top: '80px', right: '20px', zIndex: 9999, display: 'flex', flexDirection: 'column', gap: '8px' });
            $('body').append($container);
        }
        const $toast = $(`
            <div class="tana-toast d-flex align-items-center gap-2 px-3 py-2 rounded shadow">
                <i class="fa fa-check-circle text-success fa-lg"></i>
                <div>
                    <div class="fw-bold" style="font-size:13px;">${productName}</div>
                    <div class="text-muted" style="font-size:12px;">${qty} product(s) added to cart</div>
                </div>
            </div>
        `);
        $toast.css({ background: '#fff', borderLeft: '4px solid #96BC1F', minWidth: '260px', opacity: 0, transform: 'translateX(40px)', transition: 'all .3s ease' });
        $container.append($toast);
        setTimeout(() => $toast.css({ opacity: 1, transform: 'translateX(0)' }), 10);
        setTimeout(() => {
            $toast.css({ opacity: 0, transform: 'translateX(40px)' });
            setTimeout(() => $toast.remove(), 350);
        }, 3000);
    },

    _bindCartEvents() {
        const $section = this.$target;

        $section.on('click', '.tana-qty-minus', function (ev) {
            ev.preventDefault();
            const $input = $(this).siblings('.tana-qty');
            const val = parseInt($input.val(), 10) || 1;
            if (val > 1) $input.val(val - 1);
        });

        $section.on('click', '.tana-qty-plus', function (ev) {
            ev.preventDefault();
            const $input = $(this).siblings('.tana-qty');
            $input.val((parseInt($input.val(), 10) || 1) + 1);
        });

        $section.on('click', '.tana-add-to-cart', async (ev) => {
            ev.preventDefault();
            const $btn = $(ev.currentTarget);
            const $card = $btn.closest('[data-product-id]');
            const productId = parseInt($card.data('product-id'), 10);
            const qty = parseInt($card.find('.tana-qty').val(), 10) || 1;

            $btn.prop('disabled', true);
            try {
                await rpc('/shop/cart/update_json', { product_id: productId, add_qty: qty });
                this._showCartToast($card.find('h6').text().trim(), qty);
                $card.find('.tana-qty').val('1');
            } catch (e) {
                console.error('Cart update error:', e);
            } finally {
                $btn.prop('disabled', false);
            }
        });
    },
});
