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
                nextEl: ".brand-nav-next",
                prevEl: ".brand-nav-prev",
            },
            pagination: {
                el: ".brand-nav-pagination",
                clickable: true,
            },
            on: {
                init(swiper) {
                    const paginationEl = swiper.pagination.el;
                    if (paginationEl) {
                        paginationEl.style.cssText += ";position:static!important;display:flex!important;justify-content:center!important;left:unset!important;bottom:unset!important;width:100%!important;";
                    }
                },
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
