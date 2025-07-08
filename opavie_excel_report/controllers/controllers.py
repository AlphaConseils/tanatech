# -*- coding: utf-8 -*-
# from odoo import http


# class OpavieExcelReport(http.Controller):
#     @http.route('/opavie_excel_report/opavie_excel_report', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/opavie_excel_report/opavie_excel_report/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('opavie_excel_report.listing', {
#             'root': '/opavie_excel_report/opavie_excel_report',
#             'objects': http.request.env['opavie_excel_report.opavie_excel_report'].search([]),
#         })

#     @http.route('/opavie_excel_report/opavie_excel_report/objects/<model("opavie_excel_report.opavie_excel_report"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('opavie_excel_report.object', {
#             'object': obj
#         })
