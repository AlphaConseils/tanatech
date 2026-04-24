/** @odoo-module **/

import { renderToElement } from "@web/core/utils/render";
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";
import wSaleUtils from "@website_sale/js/website_sale_utils";

publicWidget.registry.NewProduct = publicWidget.Widget.extend({
    selector: '.new_products_section',

    async willStart() {
        const result = await rpc('/get_new_products', {});
        if (!result) return;

        this.$target.empty().html(renderToElement('tanatech_website.new_products_snippet', { result }));
        this._initCarousel();
        this._bindCartEvents();
    },

    _initCarousel() {
        setTimeout(() => {
            this.$target.find('.owl-carousel').owlCarousel({
                loop: true,
                margin: 20,
                nav: true,
                dots: true,
                autoplay: true,
                autoplayTimeout: 4000,
                navText: ['<i class="fa fa-chevron-left"></i>', '<i class="fa fa-chevron-right"></i>'],
                responsive: {
                    0:   { items: 1 },
                    576: { items: 2 },
                    768: { items: 3 },
                    992: { items: 4 },
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
                const cartData = await rpc('/shop/cart/update_json', { product_id: productId, add_qty: qty });
                wSaleUtils.updateCartNavBar(cartData);
                this._showCartToast($card.find('h6').text().trim(), qty);
                $card.find('.tana-qty').val(1);
            } catch (e) {
                console.error('Cart update error:', e);
            } finally {
                $btn.prop('disabled', false);
            }
        });
    },
});
