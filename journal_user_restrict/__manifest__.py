# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Journal user restrict",
    "version": "18.0.1.0.0",
    "summary": "Restrict journal access for certain users",
    "sequence": 10,
    "category": "Accounting/Accounting",
    "website": "https://www.nexources.com",
    "depends": ["account", "point_of_sale"],
    "data": ["security/ir_rule.xml", "views/account_journal_views.xml"],
    "license": "LGPL-3",
}
