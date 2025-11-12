/** @odoo-module **/

import { renderToElement } from "@web/core/utils/render";
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.homeSection = publicWidget.Widget.extend({
    selector: '.home_slide_section',
    async willStart() {
         const result = await rpc('/get_home_slide', {});
        if (result) {
            this.$target.empty().append(renderToElement('tanatech_website.home', { result }));
        }

       const $carousel = this.$target.find('.owl-carousel');

        if ($carousel.hasClass('owl-loaded')) {
            $carousel.trigger('destroy.owl.carousel');
            $carousel.removeClass('owl-loaded owl-hidden');
            $carousel.find('.owl-stage-outer').children().unwrap();
        }

        $carousel.owlCarousel({
            loop: true,
            margin: 20,
            nav: true,
            dots: true,
            autoplay: true,
            autoplayTimeout: 4000,
        });
                    
    },
});
