/** @odoo-module */
import { renderToElement } from "@web/core/utils/render";
import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";
publicWidget.registry.CategoriesProduct = publicWidget.Widget.extend({
    selector : '.categories_section',
    async willStart() {
        const result = await rpc('/get_product_categories', {});
        if(result){
            this.$target.empty().html(renderToElement('tanatech_website.category_data', {result: result}))
        }
    },
});
