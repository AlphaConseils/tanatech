# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    website_confirm_sale_activity_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="res_company_web_confirm_sale_user_rel",
        string="Sales Team (Quotation)",
        help="Users receiving an activity on the quotation when a customer "
        "confirms their order on the website. If empty, the activity is "
        "assigned to the salesperson of the order.",
    )
    website_confirm_delivery_activity_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="res_company_web_confirm_delivery_user_rel",
        string="Procurement Team (Delivery)",
        help="Users receiving an activity on the delivery order when a "
        "customer confirms their order on the website. If empty, the activity "
        "is assigned to the responsible of the transfer or to the salesperson.",
    )
    website_confirm_invoice_activity_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="res_company_web_confirm_invoice_user_rel",
        string="Finance Team (Invoicing)",
        help="Users receiving an activity on the invoice generated from a web "
        "order confirmed by the customer. If empty, the activity is assigned "
        "to the accountant of the invoice or to the salesperson.",
    )
