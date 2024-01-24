# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Tanatech Products",
    "version": "1.2",
    "category": "Sales/Sales",
    "depends": ["product"],
    "description": """
This is the base module for managing products and pricelists in Odoo.
========================================================================

Products support variants, different pricing methods, vendors information,
make to stock/order, different units of measure, packaging and properties.

Pricelists support:
-------------------
    * Multiple-level of discount (by product, category, quantities)
    * Compute price based on different criteria:
        * Other pricelist
        * Cost price
        * List price
        * Vendor price

Pricelists preferences by product and/or partners.

Print product labels with barcode.
    """,
    "data": [
        "report/report_label_product_tanatech.xml",
        "security/ir.model.access.csv",
        "views/product_template_views.xml",
    ],
    "license": "LGPL-3",
}
