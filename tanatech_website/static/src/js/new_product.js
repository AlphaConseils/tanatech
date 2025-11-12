/** @odoo-module **/

import { renderToElement } from "@web/core/utils/render";
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.NewProduct = publicWidget.Widget.extend({
    selector: '.new_products_section',
    async willStart() {
        const result = await rpc('/get_new_products', {});
        if (result) {
            this.$target.empty().html(renderToElement('tanatech_website.new_products_snippet', { result }));

            setTimeout(() => {
                this.$target.find('.owl-carousel').owlCarousel({
                    loop: true,
                    margin: 20,
                    nav: true,
                    dots: true,
                    autoplay: true,
                    autoplayTimeout: 4000,
                    navText: [
                        '<i class="fa fa-chevron-left"></i>',
                        '<i class="fa fa-chevron-right"></i>'
                    ],
                    responsive: {
                        0: { items: 1 },
                        576: { items: 2 },
                        768: { items: 3 },
                        992: { items: 4 }
                    },
                });
            }, 100);
        }
    },
});
