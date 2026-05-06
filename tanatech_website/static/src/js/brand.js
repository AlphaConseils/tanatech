/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.TanatechBrandSwiper = publicWidget.Widget.extend({
    selector: ".swiper_client",

    start() {
        new Swiper('.swiper_client', {
            loop: true,
            autoplay: {
                delay: 3000,
                disableOnInteraction: false,  // reprend après un swipe manuel
                pauseOnMouseEnter: true,      // pause au survol
            },
            pagination: {
                el: '.brand-nav-pagination',
                clickable: true,
            },
            navigation: {
                nextEl: '.brand-nav-next',
                prevEl: '.brand-nav-prev',
            },
            slidesPerView: 2,
            spaceBetween: 12,
            breakpoints: {
                576: {
                    slidesPerView: 3,
                    spaceBetween: 16,
                },
                768: {
                    slidesPerView: 4,
                    spaceBetween: 20,
                },
                992: {
                    slidesPerView: 5,
                    spaceBetween: 24,
                },
            },
        });
        return this._super(...arguments);
    },
});
