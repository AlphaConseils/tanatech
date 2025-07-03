/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ColorPickerField } from "@web/views/fields/color_picker/color_picker_field";

export class SanctionTypeColor extends ColorPickerField {
    static template = "tanatech_sanction.sanction_type_color";

    static RECORD_COLORS = [1, 2, 3, 4, 6];
}

export const sanctionTypeColorField = {
    component: SanctionTypeColor,
    supportedTypes: ["integer"],
    extractProps: ({ viewType }) => ({
        canToggle: viewType !== "list",
    }),
};

registry.category("fields").add("sanction_type_color", sanctionTypeColorField);
