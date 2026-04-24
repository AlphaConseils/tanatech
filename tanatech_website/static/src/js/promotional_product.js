/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { renderToElement } from "@web/core/utils/render";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.PromotionalProduct = publicWidget.Widget.extend({
    selector: '.promotions_section',

    async willStart() {
        const result = await rpc('/get_promotional_products', {});
        if (!result) return;

        this.$target.html(renderToElement('tanatech_website.promotional_snippet', { result }));
        this._initSwiper();
        this._bindCartEvents();
    },

    _initSwiper() {
        setTimeout(() => {
            new Swiper(".promotions-carousel", {
                slidesPerView: 4,
                grid: { rows: 2, fill: "row" },
                spaceBetween: 20,
                pagination: { el: ".swiper-pagination", clickable: true },
                navigation: { nextEl: ".swiper-button-next", prevEl: ".swiper-button-prev" },
                autoplay: { delay: 4000, disableOnInteraction: false },
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

    _updateCartCount(cartData) {
        if (!cartData || cartData.cart_quantity === undefined) return;
        const $count = $('.my_cart_quantity');
        if (!$count.length) return;
        $count.text(cartData.cart_quantity);
        const $icon = $count.closest('a');
        $icon.addClass('tana-cart-bounce');
        setTimeout(() => $icon.removeClass('tana-cart-bounce'), 600);
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
                this._updateCartCount(cartData);
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
