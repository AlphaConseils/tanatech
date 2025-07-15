/** @odoo-module **/

import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { patch } from "@web/core/utils/patch";

patch(PosOrderline.prototype, {
    get_full_product_name() {
        return this.product_id.default_code
            ? `[${this.product_id.default_code}] ${this.product_id.display_name}`
            : this.product_id.display_name;
    },
});