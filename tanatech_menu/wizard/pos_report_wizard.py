# coding: utf-8

from odoo import models

class PosReportWizard(models.TransientModel):
    _inherit='pos.details.wizard'
    
    def generate_report_bis(self):
        data = {'date_start': self.start_date, 'date_stop': self.end_date, 'config_ids': self.pos_config_ids.ids}
        return self.env.ref('tanatech_menu.sale_details_report_bis').report_action([], data=data)