/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.TanaShopCart = publicWidget.Widget.extend({
    selector: '.oe_website_sale',

    events: {
        'click .tana-qty-minus': '_onQtyMinus',
        'click .tana-qty-plus':  '_onQtyPlus',
        'click .tana-add-to-cart': '_onAddToCart',
    },

    _onQtyMinus(ev) {
        ev.preventDefault();
        const $input = $(ev.currentTarget).siblings('.tana-qty');
        const val = parseInt($input.val(), 10) || 1;
        if (val > 1) $input.val(val - 1);
    },

    _onQtyPlus(ev) {
        ev.preventDefault();
        const $input = $(ev.currentTarget).siblings('.tana-qty');
        $input.val((parseInt($input.val(), 10) || 1) + 1);
    },

    async _onAddToCart(ev) {
        ev.preventDefault();
        const $btn = $(ev.currentTarget);
        const $wrap = $btn.closest('[data-product-id]');
        const productId = parseInt($wrap.data('product-id'), 10);
        const qty = parseInt($wrap.find('.tana-qty').val(), 10) || 1;

        $btn.prop('disabled', true);
        try {
            const cartData = await rpc('/shop/cart/update_json', { product_id: productId, add_qty: qty });
            this._updateCartCount(cartData);
            const productName = $wrap.closest('form').find('h6').text().trim();
            this._showCartToast(productName, qty);
        } catch (e) {
            console.error('Cart update error:', e);
        } finally {
            $btn.prop('disabled', false);
        }
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
});
