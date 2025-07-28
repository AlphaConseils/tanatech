/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useState, useRef, onMounted } from "@odoo/owl";

export class ContractListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.rootRef = useRef("root");

        onMounted(() => {
            this._hideStatusLine();
        });
    }

    _hideStatusLine() {
        console.log(this.env.searchModel.context)
        const isCreate = this.env.searchModel.context.create
        const tbody = this.rootRef.el.querySelector("tbody");
        const rows = tbody?.querySelectorAll("tr");
        if (rows && rows.length >= 3) {
            if (isCreate == false) {
                rows[1].style.display = "none";
            } else if (isCreate == true) {
                rows[2].style.display = "none";
            } else {
                console.log('Go next')
            }
        } else {
            console.log('No rows')
        }
    }
    
}

export const contractListRenderer = {
    ...listView,
    Renderer: ContractListRenderer,
};

registry.category("views").add("contract_list_view", contractListRenderer);
