# -*-coding: utf-8 -*-
import base64
import json
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class Sanction(models.Model):
    """Handle Employee infractions"""

    _name = "sanction.sanction"
    _description = "Employee's sanction"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sanction_date desc"

    name = fields.Char(compute="_compute_employee", store=True)
    employee_id = fields.Many2one(
        comodel_name="hr.employee", string="Employee", required=True, ondelete="cascade"
    )
    image_1920 = fields.Image(related="employee_id.image_1920")
    employee_post = fields.Char(compute="_compute_employee", store=True)
    hr_responsible = fields.Many2one(
        comodel_name="res.users",
        string="HR Responsible",
    )
    hr_responsible_domain = fields.Binary(compute="_compute_hr_responsible_domain")
    employee_department = fields.Char(compute="_compute_employee", store=True)
    employee_agency = fields.Char(compute="_compute_employee", store=True)
    employee_registration_number = fields.Char(compute="_compute_employee", store=True)
    sanction_initiator = fields.Many2one(
        comodel_name="res.users", readonly=True, default=lambda self: self.env.user.id
    )
    reference = fields.Char(readonly=True)
    sanction_date = fields.Date("Sanction date")
    precursor_fact = fields.Char()
    sanction_type_id = fields.Many2one(comodel_name="sanction.type", string="Sanction")
    corrective_measure_id = fields.Many2one(
        comodel_name="sanction.corrective.measure",
        string="Corrective Measure",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("request_explanation", "Request explanation"),
            ("in_progress", "In progress"),
            ("epl", "Epl"),
            ("validate", "Validated"),
            ("refused", "Refused"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
    )
    color = fields.Integer(related="sanction_type_id.color")

    approval_request_id = fields.Many2one(
        comodel_name="approval.request", string="Approval Request"
    )
    is_validate = fields.Boolean(compute="_compute_is_validate", store=True)

    approval_ids = fields.One2many(related="approval_request_id.approver_ids")
    interview_datetime = fields.Datetime()
    interview_place = fields.Many2one(comodel_name="hr.work.location")
    demex_body = fields.Html()
    demex_date = fields.Date()
    warning_notification = fields.Html()
    epl_notification = fields.Html()
    lay_off_notification = fields.Html()
    is_lay_off = fields.Boolean(related="sanction_type_id.is_lay_off")

    employee_manager = fields.Many2one(comodel_name="res.users", readonly=False)
    emp_manager_domain = fields.Binary(compute="_compute_emp_manager_domain")

    is_long_duration = fields.Boolean("Is long duration ?")
    sanction_start_date = fields.Date("Sanction start date")
    sanction_end_date = fields.Date("Sanction end date")
    sanction_duration = fields.Float("Duration (days)")

    other_input_type_id = fields.Many2one(
        'hr.payslip.input.type',
        string="Other Input Type",
        tracking=True,
        domain=[('available_in_sanction_attachments', '=', True)]
    )

    # hr_leave_id = fields.Many2one(
    #     comodel_name="hr.leave", string="Time Off"
    # )

    hr_leave_ids = fields.One2many('hr.leave', 'sanction_id', string="Time Off")

    @api.model
    def default_get(self, fields_list):
        """Set default value on emp_manager_field"""
        defaults = super().default_get(fields_list)

        if "emp_manager_domain" in fields_list:
            managers = (
                self.env["hr.employee"]
                .search([("child_ids", "!=", False)])
                .mapped("user_id.id")
            )
            defaults["emp_manager_domain"] = json.dumps(
                [("id", "in", managers)] if managers else [("id", "in", [0])]
            )

        if "hr_responsible_domain" in fields_list:
            rh_responsible = self.sudo().env["res.users"].search([("is_rh", "=", True)])
            defaults["hr_responsible_domain"] = json.dumps(
                [("id", "in", rh_responsible.ids)]
                if rh_responsible
                else [("id", "in", [0])]
            )

        return defaults

    def _compute_emp_manager_domain(self):
        for record in self:
            managers = (
                self.sudo()
                .env["hr.employee"]
                .search([("child_ids", "!=", False)])
                .mapped("user_id.id")
            )
            record.emp_manager_domain = (
                [("id", "in", managers)] if managers else [("id", "in", [0])]
            )

    def _compute_hr_responsible_domain(self):
        for rec in self:
            rh_responsible = self.sudo().env["res.users"].search([("is_rh", "=", True)])
            rec.hr_responsible_domain = (
                [("id", "in", rh_responsible.ids)]
                if rh_responsible
                else [("id", "in", [0])]
            )

    @api.constrains("employee_id")
    def check_employee_email(self):
        """Verify email of employee"""
        for sanction in self:
            if not sanction.employee_id.work_email:
                raise ValidationError(
                    _("work email for this employee %(name)s can't be empty")
                    % {"name": sanction.employee_id.name}
                )

    def name_get(self):
        """Name of model"""
        return [(rec.id, (rec.employee_id.name, rec.sanction_type_id)) for rec in self]

    def create(self, vals_list):
        """
        Create record with manager if it's available
        """
        ref = self.env["ir.sequence"].next_by_code("sanction.sanction")
        vals_list["reference"] = ref
        if "employee_manager" not in vals_list and vals_list["employee_id"]:
            vals_list["employee_manager"] = (
                self.env["hr.employee"]
                .browse(vals_list["employee_id"])
                .parent_id.user_id.id
            )
        sanction = super().create(vals_list)
        return sanction

    @api.depends(
        "employee_id",
        "employee_id.name",
        "employee_id.job_id",
        "employee_id.parent_id",
        "employee_id.department_id",
        "employee_id.work_location_id",
    )
    def _compute_employee(self):
        """Compute employee's data"""
        for sanction in self:
            sanction.name = sanction.employee_id.name
            sanction.employee_post = sanction.employee_id.job_id.name
            sanction.employee_manager = (
                sanction.employee_id.parent_id.user_id.id
                if not sanction.employee_manager
                else sanction.employee_manager
            )
            sanction.employee_department = sanction.employee_id.department_id.name
            sanction.employee_agency = sanction.employee_id.work_location_id.name
            sanction.employee_registration_number = (
                sanction.employee_id.registration_number
            )

    def action_sanction_wizard(self):
        """open wizard to choose sanction type"""
        return {
            "name": "Sanction type ",
            "type": "ir.actions.act_window",
            "res_model": "sanction.type.wizard",
            "view_mode": "form",
            "target": "new",
        }

    def action_submit(self):
        """Prepare and send approval request then create time-off"""
        # TODO : Prepare and create unpaid time-off
        self._create_approval_request()
        self._create_unpaid_time_off()

    def action_draft(self):
        """
        Move to draft step
        """
        if self.state not in "cancel":
            raise ValidationError(_("Sanction must be cancel before"))
        self.state = "draft"
        self.sanction_type_id = False
        self.demex_date = False
        self.precursor_fact = ""
        self.is_validate = False
        self.warning_notification = False
        if self.hr_leave_ids:
            self.hr_leave_ids.action_reset_confirm()
            self.hr_leave_ids.unlink()

    def action_cancel_sanction(self):
        """Cancel Sanction"""
        self.state = "cancel"
        self.approval_request_id.action_cancel()
        if self.hr_leave_ids:
            self.hr_leave_ids.action_refuse()
            # self.hr_leave_ids.write({'state': 'cancel'})

    def action_send_mail(self):
        """Send explanation request email"""
        # request explanation
        self.ensure_one()
        if not self.employee_manager:
            raise ValidationError(_("Manager field cannot by empty"))

        if not self.hr_responsible:
            raise ValidationError(_("Responsible RH field cannot by empty"))

        template = self.env.ref("tanatech_sanction.sanction_demex_mail_template")
        # compose_form = self.env.ref(
        #     "mail.email_compose_message_wizard_form", raise_if_not_found=False
        # )
        compose_form_id = self.env['ir.model.data']._xmlid_to_res_id('mail.email_compose_message_wizard_form')
        ctx = {
            "default_model": "sanction.sanction",
            "default_res_ids": self.ids,
            "default_template_id": template.id if template else False,
            "default_composition_mode": "comment",
            "default_email_layout_xmlid": "mail.mail_notification_light",
        }
        return {
            "name": _("Demex Email"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mail.compose.message",
            "views": [(compose_form_id, "form")],
            "view_id": compose_form_id,
            "target": "new",
            "context": ctx,
        }

    def _create_approval_request(self):
        """Create approval request"""
        for rec in self:
            self._prepare_approval_request(rec=rec)

    def _prepare_approval_request(self, rec):
        """Prepare all data for approval request"""
        category_id = self.env.ref("tanatech_sanction.approval_category_sanction")
        if not rec.employee_manager:
            raise ValidationError(
                _("Set manager for %(employee_name)s")
                % {"employee_name": rec.employee_id.name}
            )

        if rec.hr_responsible.id:
            # case : employee_id.parent_id == hr_responsable
            category_id.approval_minimum = (
                1 if rec.hr_responsible.id == rec.employee_manager.id else 2
            )

            approver_ids = [(0, 0, {"user_id": rec.hr_responsible.id})]
            if rec.hr_responsible.id != rec.employee_manager.id:
                approver_ids.append((0, 0, {"user_id": rec.employee_manager.id}))
                category_id.approver_sequence = True
        else:
            category_id.approval_minimum = 1
            approver_ids = [(0, 0, {"user_id": rec.employee_manager.id})]

        approval_request = self.env["approval.request"].create(
            {
                "name": _("Sanction : %(name)s - %(type_name)s")
                % {"name": rec.name, "type_name": rec.sanction_type_id.name},
                "request_owner_id": self.env.user.id,
                "category_id": category_id.id,
                "sanction_id": rec.ids,
                "approver_ids": approver_ids,
            }
        )

        rec.approval_request_id = approval_request.id
        rec.approval_request_id.action_confirm()

    def _create_unpaid_time_off(self):
        """Create Time-off"""
        for rec in self:
            self._prepare_unpaid_time_off(record=rec)

    def _prepare_unpaid_time_off(self, record):
        """ Prepare and create an unpaid time-off related to the sanction 
            in order to have a view in time-off dashboar and payroll work entries 
        """
        if record.sanction_type_id.is_taken_into_account_in_time_off:
            hr_leave_type = self.env["hr.leave.type"].search([('specific_for_sanction', '=', True)], limit=1)
            if not hr_leave_type:
                return
            duration_display = (_(
                "%(sanction_duration)s days"
                ) % {"sanction_duration": record.sanction_duration}
            )
            hr_leave = self.env["hr.leave"].create(
                {
                    "name": _("%(name)s on %(time_off_type)s: %(duration_display)s")
                    % {"name": record.employee_id.name, "time_off_type": hr_leave_type.name, "duration_display": duration_display},
                    "employee_id": record.employee_id.id,
                    "company_id": record.employee_id.company_id.id,
                    "department_id": record.employee_id.department_id.id,
                    "holiday_status_id": hr_leave_type.id,
                    "payslip_state": "normal",
                    "request_date_from": record.sanction_date if not record.is_long_duration else record.sanction_start_date,
                    "request_date_to": record.sanction_date if not record.is_long_duration else record.sanction_end_date,
                    "state": "confirm",
                }
            )
            # record.hr_leave_id = hr_leave.id
            record.hr_leave_ids = [(4, hr_leave.id)]
        else:
            return

    is_related_to_time_off = fields.Boolean("Is related to time-off ?", compute="_check_if_related_to_time_off")

    @api.depends('sanction_type_id')
    def _check_if_related_to_time_off(self):
        for record in self:
            if not record.sanction_type_id:
                record.is_related_to_time_off = False
            else:
                record.is_related_to_time_off = record.sanction_type_id.is_taken_into_account_in_time_off

    def _validate_time_off_record(self, record):
        record.hr_leave_ids.action_approve()

    def _get_teamplate_and_report_warning(self):
        """Define template and report action warning"""
        template = self.sudo().env.ref("tanatech_sanction.sanction_warning_mail_template")
        if self.warning_notification:
            template.body_html = self.warning_notification
        action_report = self.sudo().env.ref("tanatech_sanction.action_report_warning")
        return template, action_report

    def _get_teamplate_and_report_epl(self):
        """Define template and report action EPL"""
        template = self.sudo().env.ref("tanatech_sanction.sanction_epl_mail_template")
        if self.epl_notification:
            template.body_html = self.epl_notification
        action_report = self.sudo().env.ref("tanatech_sanction.action_report_epl")
        return template, action_report

    def _get_teamplate_and_report_lay_off(self):
        """Define template and report action lay off"""
        template = self.sudo().env.ref("tanatech_sanction.lay_off_mail_template")
        if self.lay_off_notification:
            template.body_html = self.lay_off_notification
        action_report = self.sudo().env.ref("tanatech_sanction.action_lay_off_report")
        return template, action_report

    @api.depends("approval_request_id.request_status")
    def _compute_is_validate(self):
        """Compute is validate field in different step of approvals"""
        for rec in self:
            if rec.approval_request_id.request_status == "pending":
                if rec.state == "epl" and not rec.is_validate:
                    continue
                rec.state = "in_progress"
                rec.is_validate = False
            elif rec.approval_request_id.request_status == "approved":

                if not rec.is_lay_off:
                    rec.state = "validate"
                    rec.is_validate = True
                    template, action_report = self._get_teamplate_and_report_warning()
                    rec._send_notification_mail(
                        template=template, action_report=action_report
                    )
                    self._validate_time_off_record(record=rec)
                elif rec.is_lay_off and rec.state not in "epl":
                    # EPL STAGE
                    rec.is_validate = False
                    rec.state = "epl"
                    template, action_report = self._get_teamplate_and_report_epl()
                    rec._send_notification_mail(
                        template=template, action_report=action_report
                    )
                    rec._prepare_approval_request(rec=rec)
                elif rec.is_lay_off and rec.state in "epl":
                    # LAY OFF STAGE
                    rec.is_validate = True
                    rec.state = "validate"
                    template, action_report = self._get_teamplate_and_report_lay_off()
                    rec._send_notification_mail(
                        template=template, action_report=action_report
                    )
                    self._validate_time_off_record(record=rec)
            elif rec.approval_request_id.request_status == "refused":
                rec.state = "refused"
                rec.is_validate = False

    def _prepare_email_action(self, notification_type, notification_body, template):
        """
        Prépare une action pour composer un email basé sur le type,
        le contenu de notification et le template.
        """
        self.ensure_one()
        if notification_body:
            template.body_html = notification_body
        else:
            template.reset_template()

        # compose_form = self.env.ref(
        #     "mail.email_compose_message_wizard_form", raise_if_not_found=False
        # )
        compose_form_id = self.env['ir.model.data']._xmlid_to_res_id('mail.email_compose_message_wizard_form')
        ctx = {
            "default_model": "sanction.sanction",
            "default_res_ids": self.ids,
            "default_template_id": template.id if template else False,
            "default_composition_mode": "comment",
            "default_email_layout_xmlid": "mail.mail_notification_light",
            "default_sanction_type": self.sanction_type_id,
            "default_notification_type": notification_type,
        }
        return {
            "name": (
                _("EPL Email")
                if notification_type == "epl"
                else (
                    _("Warning Email")
                    if notification_type == "warning"
                    else _("Lay Off")
                )
            ),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mail.compose.message",
            "views": [(compose_form_id, "form")],
            "view_id": compose_form_id,
            "target": "new",
            "context": ctx,
        }

    def action_write_warning_email(self):
        """
        Write warning email
        """
        template = self.env.ref("tanatech_sanction.sanction_warning_mail_template")
        return self._prepare_email_action(
            notification_type="warning",
            notification_body=self.warning_notification,
            template=template,
        )

    def action_write_epl_email(self):
        """
        Write EPL email
        """
        self.ensure_one()
        template = self.env.ref("tanatech_sanction.sanction_epl_mail_template")
        return self._prepare_email_action(
            notification_type="epl",
            notification_body=self.epl_notification,
            template=template,
        )

    def action_apercu_warning_email(self):
        """
        Show warning email
        """
        return self.action_write_warning_email()

    def action_apercu_epl_email(self):
        """Show epl email"""
        return self.action_write_epl_email()

    def action_write_lay_off_email(self):
        """
        Write Lay off email
        """
        template = self.env.ref("tanatech_sanction.lay_off_mail_template")
        return self._prepare_email_action(
            notification_type="lay_off",
            notification_body=self.lay_off_notification,
            template=template,
        )

    def action_apercu_lay_off_email(self):
        """
        Show Lay off  email
        """
        return self.action_write_lay_off_email()

    def _generate_email_pdf(self, action_report):
        """Generate email to pdf"""
        report_action = action_report
        pdf_content, _ = (
            self.sudo()
            .env["ir.actions.report"]
            ._render_qweb_pdf(report_action.id, [self.id])
        )
        return pdf_content

    def _create_attachment(self, pdf_content, active_model):
        """Attach pdf on email"""
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"{self.sanction_type_id.name}_{self.employee_id.name}.pdf",
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "res_model": active_model,
                "res_id": self.id,
                "mimetype": "application/pdf",
            }
        )

        return attachment

    def _send_notification_mail(self, template, action_report):
        """
        Send notfication email or Epl if it's lay off after approval user(s) validate
        """
        self.ensure_one()
        pdf_content = self._generate_email_pdf(action_report=action_report)
        attachment = self._create_attachment(
            pdf_content=pdf_content, active_model=self._name
        )

        self.message_post(
            subject=template.subject,
            body=template.body_html,
            partner_ids=self.employee_id.user_partner_id.ids,
            attachment_ids=attachment.ids,
            body_is_html=True,
            subtype_xmlid="mail.mt_comment",
        )

    def get_sign_signature_demex(self):
        """Get signature with sudo access."""
        self.ensure_one()
        return (
            self.env.user.sudo().sign_signature
            if self.env.user.sudo().sign_signature
            else None
        )

    def get_signature_manager(self):
        """Return manager's signature"""
        return (
            self.employee_manager.sudo().sign_signature
            if self.employee_manager.sudo().sign_signature
            else None
        )

    def get_signature_rh_responsible(self):
        """Return rh responsible's signature"""
        return (
            self.hr_responsible.sudo().sign_signature
            if self.hr_responsible and self.hr_responsible.sudo().sign_signature
            else None
        )
    
    def open_sanction(self):
        """
        Open sanction view form from employee and if current user is manager
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Sanctions',
            'view_mode': 'form',
            'res_model': 'sanction.sanction',
            'res_id': self.id,
            'context': "{'create': False}",
        }
