from odoo import models


class HrContract(models.Model):
    _inherit = "hr.contract"

    def generate_work_entries(self, date_start, date_stop, force=False):
        work_entries = super().generate_work_entries(date_start, date_stop, force)
        work_entries.auto_update_overtime_work_entry_type()
        return work_entries
