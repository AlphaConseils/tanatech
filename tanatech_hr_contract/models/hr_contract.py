# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date

from odoo.osv import expression


class HrContract(models.Model):
    _inherit = "hr.contract"

    family_allowance = fields.Monetary(
        "Family Allowance",
        required=True,
        tracking=True,
        help="Employee's monthly family allocation.",
    )

    resource_calendar_id = fields.Many2one('resource.calendar', copy=True)

    kanban_state = fields.Selection(copy=True)

    contract_id = fields.Many2one('hr.contract', string='Source Contract', index=True)

    # state = fields.Selection(selection_add=[('open_not_declared', 'Running Undeclared')])
    state = fields.Selection([
        ('draft', 'New'),
        ('open', 'Running'),
        ('open_not_declared', 'Running Undeclared'),
        ('close', 'Expired'),
        ('cancel', 'Cancelled')
    ], string='Status', group_expand=True, copy=True,
        tracking=True, help='Status of the contract', default='draft')

    contract_category = fields.Selection(
        selection=[
            ('declared', "Declared"),
            ('not_declared', "Undeclared"),
        ],
        string="Contract Category",
        default="declared",
        store=True
    )

    @api.constrains('employee_id', 'state', 'kanban_state', 'date_start', 'date_end')
    def _check_current_contract(self):
        """ Two contracts in state [incoming | open | close] cannot overlap """
        for contract in self.filtered(lambda c: (c.state not in ['draft', 'open_not_declared', 'cancel'] or c.state == 'draft' and c.kanban_state == 'done') and c.employee_id):
            domain = [
                ('id', '!=', contract.id),
                ('employee_id', '=', contract.employee_id.id),
                ('company_id', '=', contract.company_id.id),
                ('contract_category', '!=', 'not_declared'),
                '|',
                    ('state', 'in', ['open', 'close']),
                    '&',
                        ('state', '=', 'draft'),
                        ('kanban_state', '=', 'done') # replaces incoming
            ]

            if not contract.date_end:
                start_domain = []
                end_domain = ['|', ('date_end', '>=', contract.date_start), ('date_end', '=', False)]
            else:
                start_domain = [('date_start', '<=', contract.date_end)]
                end_domain = ['|', ('date_end', '>', contract.date_start), ('date_end', '=', False)]

            domain = expression.AND([domain, start_domain, end_domain])
            # conflicts = self.search_count(domain)
            conflicts = self.search(domain)
            if conflicts:
                raise ValidationError(
                    _(
                        'An employee can only have one contract at the same time. (Excluding Draft and Cancelled contracts).\n\nEmployee: %(employee_name)s',
                        employee_name=contract.employee_id.name
                    )
                )

    def unlink(self):
        for contract in self:
            if contract.contract_category == 'not_declared':
                raise ValidationError(_('Undeclared contract cannot be removed explicitly! \nTips : Remove the declared contract.'))
            else:
                not_declared_contract = self.env['hr.contract'].search([('contract_id', '=', contract.id), ('contract_category', '=', 'not_declared')], limit=1)
                if not_declared_contract:
                    # FIXME : Gotta find a wiser way to erase data apart from using raw SQL like this,
                    # in bid to unlink all related stuff such as payslip and so on.
                    self.env.cr.execute("""
                        DELETE FROM hr_contract
                        WHERE id = %s; 
                    """, (not_declared_contract.id,))
                    self.env.cr.commit()
        return super().unlink()

    def action_archive(self):
        """ Override to archive the associated undeclared contract before archiving the declared one. """
        for contract in self:
            if contract.contract_category == 'not_declared':
                raise ValidationError(_('Undeclared contract cannot be archived explicitly! \nTips : Archive the declared contract.'))
            else:
                not_declared_contract = self.env['hr.contract'].search([('contract_id', '=', contract.id), ('contract_category', '=', 'not_declared')], limit=1)
                if not_declared_contract:
                    # FIXME : Gotta find a wiser way to do this action apart from using raw SQL like this.
                    self.env.cr.execute("""
                        UPDATE hr_contract
                        SET active = 'false'
                        WHERE id = %s;  
                    """, (not_declared_contract.id,))
                    self.env.cr.commit()
        return super().action_archive()

    def action_unarchive(self):
        """ Override to unarchive the associated undeclared contract before unarchiving the declared one. """
        for contract in self:
            if contract.contract_category == 'not_declared':
                raise ValidationError(_('Undeclared contract cannot be unarchived explicitly! \nTips : Unarchive the declared contract.'))
            else:
                not_declared_contract = self.env['hr.contract'].search([('contract_id', '=', contract.id), ('contract_category', '=', 'not_declared'), ('active', '=', False)], limit=1)
                if not_declared_contract:
                    # FIXME : Gotta find a wiser way to do this action apart from using raw SQL like this.
                    self.env.cr.execute("""
                        UPDATE hr_contract
                        SET active = 'true'
                        WHERE id = %s;  
                    """, (not_declared_contract.id,))
                    self.env.cr.commit()
        return super().action_unarchive()

    @api.model_create_multi
    def create(self, vals_list):
        """ Affect the default undeclared structure type for undeclared contract """
        contracts = super().create(vals_list)
        for contract in contracts.filtered(lambda c: c.contract_category == 'not_declared'):
            structure_type = self.env['hr.payroll.structure.type'].search([('structure_category', '=', 'not_declared')], limit=1)
            if not structure_type:
                continue
            contract.structure_type_id = structure_type.id
        return contracts

    def write(self, vals):
        # TODO : set the default 'structure_type_id' for undeclared contract
        res = super(HrContract, self).write(vals)
        # FIXME : Find a better way to update the undeclared contract other than raw SQL
        for contract in self:
            not_declared_contract = self.env['hr.contract'].search([('contract_id', '=', contract.id), ('contract_category', '=', 'not_declared')], limit=1)
            if 'state' in vals:
                if vals.get('state') == 'open':
                    if not not_declared_contract:
                        new_not_declared_contract = contract.copy({
                            'name' : f'{contract.name} - N.D.',
                            'date_start' : contract.date_start,
                            'contract_category' : 'not_declared',
                            'state' : 'open_not_declared',
                            'contract_id' : contract.id,
                        })
                    else:
                        self.env.cr.execute("""
                            UPDATE hr_contract
                            SET state = 'open_not_declared'
                            WHERE id = %s; 
                        """, (not_declared_contract.id,))
                        self.env.cr.commit()
                elif vals.get('state') == 'draft':
                    if not_declared_contract:
                        self.env.cr.execute("""
                            UPDATE hr_contract
                            SET state = 'draft'
                            WHERE id = %s; 
                        """, (not_declared_contract.id,))
                        self.env.cr.commit()
                    else:
                        new_not_declared_contract = contract.copy({
                            'name' : f'{contract.name} - N.D.',
                            'date_start' : contract.date_start,
                            'contract_category' : 'not_declared',
                            'state' : 'draft',
                            'contract_id' : contract.id,
                        })
                elif vals.get('state') == 'close':
                    if not_declared_contract:
                        self.env.cr.execute("""
                            UPDATE hr_contract
                            SET state = 'close', date_end = %s
                            WHERE id = %s; 
                        """, (contract.date_end, not_declared_contract.id))
                        self.env.cr.commit()
                    else:
                        new_not_declared_contract = contract.copy({
                            'name' : f'{contract.name} - N.D.',
                            'date_start' : contract.date_start,
                            'date_end' : contract.date_end,
                            'contract_category' : 'not_declared',
                            'state' : 'close',
                            'contract_id' : contract.id,
                        })
                else:
                    if not_declared_contract:
                        self.env.cr.execute("""
                            UPDATE hr_contract
                            SET state = 'cancel'
                            WHERE id = %s; 
                        """, (not_declared_contract.id,))
                        self.env.cr.commit()
                    else:
                        new_not_declared_contract = contract.copy({
                            'name' : f'{contract.name} - N.D.',
                            'date_start' : contract.date_start,
                            'contract_category' : 'not_declared',
                            'state' : 'cancel',
                            'contract_id' : contract.id,
                        })
            # employee_id
            if 'employee_id' in vals:
                if not_declared_contract:
                    self.env.cr.execute("""
                        UPDATE hr_contract
                        SET employee_id = %s, job_id = %s, department_id = %s, resource_calendar_id = %s, company_id = %s
                        WHERE id = %s; 
                    """, (
                            contract.employee_id.id if contract.employee_id else None, 
                            contract.employee_id.job_id.id if contract.employee_id.job_id else None, 
                            contract.employee_id.department_id.id if contract.employee_id.department_id else None, 
                            contract.employee_id.resource_calendar_id.id if contract.employee_id.resource_calendar_id else None, 
                            contract.employee_id.company_id.id if contract.employee_id.company_id else None, 
                            not_declared_contract.id,
                        )
                    )
                    self.env.cr.commit()
            # contract_type_id
            if 'contract_type_id' in vals:
                if not_declared_contract:
                    self.env.cr.execute("""
                        UPDATE hr_contract
                        SET contract_type_id = %s
                        WHERE id = %s; 
                    """, (
                            contract.contract_type_id.id if contract.contract_type_id else None,
                            not_declared_contract.id,
                        )
                    )
                    self.env.cr.commit()
            # Dates
            if 'date_start' in vals:
                if not_declared_contract:
                    self.env.cr.execute("""
                        UPDATE hr_contract
                        SET date_start = %s
                        WHERE id = %s; 
                    """, (
                            contract.date_start,
                            not_declared_contract.id,
                        )
                    )
                    self.env.cr.commit()
            if 'date_end' in vals:
                if not_declared_contract:
                    self.env.cr.execute("""
                        UPDATE hr_contract
                        SET date_end = %s
                        WHERE id = %s; 
                    """, (
                            contract.date_end if contract.date_end else None,
                            not_declared_contract.id,
                        )
                    )
                    self.env.cr.commit()
            # resource_calendar_id
            if 'resource_calendar_id' in vals:
                if not_declared_contract:
                    self.env.cr.execute("""
                        UPDATE hr_contract
                        SET resource_calendar_id = %s
                        WHERE id = %s; 
                    """, (
                            contract.resource_calendar_id.id,
                            not_declared_contract.id,
                        )
                    )
                    self.env.cr.commit()
            # name
            if 'name' in vals:
                if not_declared_contract:
                    name = f"{contract.name} - N.D."
                    self.env.cr.execute("""
                        UPDATE hr_contract
                        SET name = %s
                        WHERE id = %s; 
                    """, (
                            name,
                            not_declared_contract.id,
                        )
                    )
                    self.env.cr.commit()
        return res

    def _set_to_draft(self):
        for contract in self:
            if contract.contract_category == 'not_declared':
                raise ValidationError(_('Cannot modify undeclared contract status !'))
            if contract.state != 'draft':
                contract.write({
                    'state': 'draft'
                })

    def _set_to_running(self):
        for contract in self:
            if contract.contract_category == 'not_declared':
                raise ValidationError(_('Cannot modify undeclared contract status !'))
            if contract.state != 'open':
                contract.write({
                    'state': 'open'
                })

    def _set_to_expired(self):
        for contract in self:
            if contract.contract_category == 'not_declared':
                raise ValidationError(_('Cannot modify undeclared contract status !'))
            if contract.state != 'close':
                contract.write({
                    'state': 'close'
                })

    def _set_to_cancelled(self):
        for contract in self:
            if contract.contract_category == 'not_declared':
                raise ValidationError(_('Cannot modify undeclared contract status !'))
            if contract.state != 'cancel':
                contract.write({
                    'state': 'cancel'
                })