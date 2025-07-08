# -*- coding:utf-8 -*-
from odoo import api, Command, models, fields


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    sanction_count = fields.Integer(compute='_compute_sanction_count') 

    def action_open_sanctions(self):
        self.ensure_one()
        # sanctions = self.env['sanction.sanction'].search([('state', '!=', 'draft'),('employee_id', '=', self.employee_id.id)])
        # if len(sanctions) == 1:
        #     return {
        #         'type': 'ir.actions.act_window',
        #         'name': 'Sanctions',
        #         'view_mode': 'form',
        #         'res_model': 'sanction.sanction',
        #         'res_id': sanctions.id,
        #         'context': "{'create': False}",
        #     }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sanctions',
            'view_mode': 'list,form',
            'res_model': 'sanction.sanction',
            'domain': [('employee_id', '=', self.employee_id.id)],
            'context': "{'create': False}",
        }
    
    def _compute_sanction_count(self):
        for payslip in self:
            payslip.sanction_count = self.env['sanction.sanction'].search_count([
                ('state', '!=', 'draft'),
                ('employee_id', '=', payslip.employee_id.id)
                ])

    @api.depends('employee_id', 'contract_id', 'struct_id', 'date_from', 'date_to', 'struct_id')
    def _compute_input_line_ids(self):
        super()._compute_input_line_ids()
        for payslip in self:
            sanction_attachment_type_ids = self.env['hr.payslip.input.type'].search([('available_in_sanction_attachments', '=', True)]).ids
            if payslip.employee_id.contract_id and payslip.date_to:
                lines_to_remove = payslip.input_line_ids.filtered(lambda x: x.input_type_id.id in sanction_attachment_type_ids)
                input_sanction_line_vals = [Command.unlink(line.id) for line in lines_to_remove]
                # sanctions = self.env['sanction.sanction'].search([('state', '!=', 'draft'),('employee_id', '=', self.employee_id.id)])
                sanctions = payslip.employee_id.sanction_ids.filtered(
                    lambda san: san.state == 'validate'
                        and san.sanction_start_date <= payslip.date_to if san.is_long_duration else san.sanction_date <= payslip.date_to
                        and san.other_input_type_id.available_in_sanction_attachments == True
                )
                if sanctions:
                    name = ', '.join(sanctions.mapped('sanction_type_id.name'))
                    duration = sum(sanction.sanction_duration for sanction in sanctions)
                    amount = (payslip.employee_id.contract_id.wage/30)*duration
                    # input_type_id = self.env['hr.payslip.input.type'].search([('available_in_sanction_attachments', '=', True)], limit=1)
                    input_type_id = sanctions[0].other_input_type_id
                    input_sanction_line_vals.append(
                        Command.create({
                            'name': name,
                            'amount': -amount,
                            'input_type_id': input_type_id.id,
                        })
                    )
                payslip.update({'input_line_ids': input_sanction_line_vals})