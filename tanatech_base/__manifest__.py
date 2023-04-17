# -*- coding: utf-8 -*-
{
    "name": "Tanatech Base",
    "summary": """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",
    "description": """
        Long description of module's purpose
    """,
    "author": "Nexources",
    "website": "http://www.nexources.com",
    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    "category": "Uncategorized",
    "version": "0.1",
    # any module necessary for this one to work correctly
    "depends": ["base"],
    # always loaded
    "data": [
        # report
        "report/a5.xml",
        "report/external_layout_standard.xml",
    ],
    "assets": {"web.assets_backend": ["tanatech_base/static/src/scss/bg.scss"]},
}
