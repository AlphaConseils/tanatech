/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { renderToElement } from "@web/core/utils/render";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.get_promotions_swiper = publicWidget.Widget.extend({
    selector: '.promotions_section',
    async willStart() {
        const result = await rpc('/get_promotional_products', {});
        if (result) {
            this.$target.html(renderToElement('tanatech_website.promotional_snippet', { result }));

            setTimeout(() => {
                new Swiper(".promotions-carousel", {
                    slidesPerView: 4,
                    grid: {
                        rows: 2,
                        fill: "row"
                    },
                    spaceBetween: 20,
                    pagination: {
                        el: ".swiper-pagination",
                        clickable: true,
                    },
                    navigation: {
                        nextEl: ".swiper-button-next",
                        prevEl: ".swiper-button-prev",
                    },
                    autoplay: {
                        delay: 4000,
                        disableOnInteraction: false,
                    },
                    watchOverflow: true,

                    breakpoints: {
                        0: {
                            slidesPerView: 1,
                            grid: { rows: 2 }
                        },
                        576: {
                            slidesPerView: 2,
                            grid: { rows: 2 }
                        },
                        768: {
                            slidesPerView: 3,
                            grid: { rows: 2 }
                        },
                        992: {
                            slidesPerView: 4,
                            grid: { rows: 2 }
                        }
                    }
                });
            }, 100);
        }
    }
});
