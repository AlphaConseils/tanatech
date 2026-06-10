# -*- coding: utf-8 -*-
{
    "name": "Tanatech - Approvals",
    "summary": "A module to manage approval processes within the Tanatech system.",
    "author": "Nexources",
    "website": "https://www.nexources.com",
    "category": "Uncategorized",
    "version": "0.1",
    "depends": ["approvals", "purchase", "hr_expense", "documents_hr_expense"],
    "data": [
        # 'security/ir.model.access.csv',
        "views/approval_category_views.xml",
        "views/approval_product_line_views.xml",
        "views/approval_request_view.xml",
        "views/hr_expenses_views.xml",
    ],
}
