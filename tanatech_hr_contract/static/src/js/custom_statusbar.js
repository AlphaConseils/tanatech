/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { statusBarField, StatusBarField } from "@web/views/fields/statusbar/statusbar_field";

export class ContractCustomizedStatusbarStatusbar extends StatusBarField {
    setup() {
        super.setup();
    }

    getAllItems() {
        const currentState = this.props.record.data[this.props.name];
        const currentCategoryTypeUndeclared = this.props.record.data.contract_category;
        let allItems = super.getAllItems();
        
        // remove 'open' in the statusbar_visible for undeclared contract
        if (currentCategoryTypeUndeclared === 'not_declared') {
            allItems = allItems.filter((item) => item.value !== 'open')
        } else {
            allItems = allItems.filter((item) => item.value !== 'open_not_declared')
        }
    
        return allItems;
    }    

}

export const contractCustomizedStatusbarStatusbar = {
    ...statusBarField,
    component: ContractCustomizedStatusbarStatusbar,
    displayName: _t("Undeclared Contract Status"),
    supportedTypes: ["state", "selection"],
    additionalClasses: ["o_field_statusbar"],
};

registry.category("fields").add("statusbar_undeclared_contract", contractCustomizedStatusbarStatusbar);

// registry.category("fields").add("statusbar", {
//     component: ContractCustomizedStatusbarStatusbar,
//     displayName: "dynamic statusbar for undeclated contract",
//     supportedTypes: ["many2one", "selection"],
//     supportedOptions: [],
//     isEmpty: (record, fieldName) => !record.data[fieldName],
//     extractProps: ({ attrs, options, viewType }, dynamicInfo) => ({
//         isDisabled: !options.clickable || dynamicInfo.readonly,
//         visibleSelection: attrs.statusbar_visible?.trim().split(/\s*,\s*/g),
//         withCommand: viewType === "form",
//         foldField: options.fold_field,
//         domain: dynamicInfo.domain(),
//     }),
// }, { force: true });
