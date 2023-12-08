# -*- coding: utf-8 -*-
# from odoo import http


# class TanatechReport(http.Controller):
#     @http.route('/tanatech_report/tanatech_report', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/tanatech_report/tanatech_report/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('tanatech_report.listing', {
#             'root': '/tanatech_report/tanatech_report',
#             'objects': http.request.env['tanatech_report.tanatech_report'].search([]),
#         })

#     @http.route('/tanatech_report/tanatech_report/objects/<model("tanatech_report.tanatech_report"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('tanatech_report.object', {
#             'object': obj
#         })
