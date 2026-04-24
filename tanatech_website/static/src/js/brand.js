/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.TanatechBrandSwiper = publicWidget.Widget.extend({
    selector: ".swiper_client",

    start() {
        new Swiper(this.el, {
            direction: "horizontal",
            loop: true,
            loopAdditionalSlides: 7,
            spaceBetween: 20,
            speed: 2000,
            autoplay: {
                delay: 3000,
                disableOnInteraction: false,
            },
            navigation: {
                nextEl: ".navigation-swip .fa-arrow-right",
                prevEl: ".navigation-swip .fa-arrow-left",
            },
            breakpoints: {
                300: { slidesPerView: 1.5 },
                600: { slidesPerView: 2.5 },
                900: { slidesPerView: 3 },
                1200: { slidesPerView: 5 },
            },
        });
        return this._super(...arguments);
    },
});
