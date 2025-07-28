/** @odoo-module **/

import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { useState, useRef, onMounted } from "@odoo/owl";

export class ContracKanbanRenderer extends KanbanRenderer {
    setup() {
        super.setup();
        this.rootRef = useRef("root");

        onMounted(() => {
            this._hideStatusColumn();
        });
    }

    _hideStatusColumn() {
        const isCreate = this.env.searchModel.context.create
        const columns = this.rootRef.el.querySelectorAll(".o_kanban_group");
        if (columns && columns.length >= 3) {
            if (isCreate == false) {
                columns[1].style.display = "none";  // 0-based index → 2nd column
            } else if (isCreate == true) {
                columns[2].style.display = "none";
            } else {
                console.log('Go next')
            }
        } else {
            console.log('No columns')
        }
    }
    
}

export const contracKanbanRenderer = {
    ...kanbanView,
    Renderer: ContracKanbanRenderer,
};

registry.category("views").add("contract_kanban_view", contracKanbanRenderer);
