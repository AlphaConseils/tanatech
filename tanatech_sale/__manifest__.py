{  # noqa: B018
    "name": "Tanatech Sale",
    "version": "1.2",
    "website": "https://www.nexources.com/",
    "category": "Services/Project",
    "sequence": 999,
    "depends": ["sale", "base", "tanatech_base", "purchase"],
    "data": [
        # data
        "data/sale_config.xml",
        # security
        "security/res_groups.xml",
        # views
        "views/sale_order_views.xml",
        "views/res_partner_views.xml",
        # report
        "report/sale_report.xml",
        "report/inherit_report_saleorder_document.xml",
        "report/supplier_report.xml",
        "report/inherit_report_purchaseorder_document.xml",
        "report/report_saleorder_document_inherited.xml",
    ],
    "license": "LGPL-3",
}
