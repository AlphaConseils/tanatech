/** @odoo-module **/

import { registry } from "@web/core/registry";
import { StatusBarField } from "@web/views/fields/statusbar/statusbar_field";

export class CustomizedStatusbarStatusbar extends StatusBarField {
    setup() {
        super.setup();
    }

    getAllItems() {
        const currentState = this.props.record.data[this.props.name];
        const currentSanctionTypeIsLayOff = this.props.record.data.is_lay_off;
        let allItems = super.getAllItems();
    
        // Helper: avoids duplicate entries
        const exists = (value) => allItems.some(item => item.value === value);
    
        // insert 'epl' in the statusbar_visible
        if (currentSanctionTypeIsLayOff && !exists('epl')) {
            const validateIndex = allItems.findIndex(item => item.value === 'validate');
            if (validateIndex !== -1) {
                const eplItem = {
                    value: 'epl',
                    label: 'Epl',
                    isFolded: false,
                    isSelected: false,
                };
                allItems = [
                    ...allItems.slice(0, validateIndex),
                    eplItem,
                    ...allItems.slice(validateIndex),
                ];
            }
        }
    
        return allItems;
    }    

}

registry.category("fields").add("statusbar", {
    component: CustomizedStatusbarStatusbar,
    displayName: "Barre d'etat dynamique",
    supportedTypes: ["many2one", "selection"],
    supportedOptions: [],
    isEmpty: (record, fieldName) => !record.data[fieldName],
    extractProps: ({ attrs, options, viewType }, dynamicInfo) => ({
        isDisabled: !options.clickable || dynamicInfo.readonly,
        visibleSelection: attrs.statusbar_visible?.trim().split(/\s*,\s*/g),
        withCommand: viewType === "form",
        foldField: options.fold_field,
        domain: dynamicInfo.domain(),
    }),
}, { force: true });
