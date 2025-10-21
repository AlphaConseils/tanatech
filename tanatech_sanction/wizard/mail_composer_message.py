# -*- coding: utf-8 -*-
import base64
from odoo import models, fields


class MailComposeMessage(models.TransientModel):
    _inherit = "mail.compose.message"

    def _get_sanction(self):
        active_model = self.env.context.get("default_model")

        if active_model == "sanction.sanction":
            sanction = self.env[active_model].browse(self.env.context["active_id"])
        return sanction

    def action_send_mail(self):
        """purpose : change state of sanction if mail sent"""
        active_model = self.env.context.get("default_model")
        if active_model == "sanction.sanction": 
            sanction = self._get_sanction()
            pdf_content = self._generate_email_pdf(sanction)
            self._create_attachment(
                sanction, pdf_content, self.env.context.get("default_model")
            )
            sanction.state = "request_explanation"
            sanction.demex_date = fields.Date.today()

        super(MailComposeMessage, self).action_send_mail()

    def _generate_email_pdf(self, sanction):
        sanction.demex_body = self.body
        report_action = self.sudo().env.ref("tanatech_sanction.action_report_demex")
        pdf_content, _ = (
            self.sudo()
            .env["ir.actions.report"]
            ._render_qweb_pdf(report_action.id, [sanction.id])
        )
        return pdf_content

    def _create_attachment(self, sanction, pdf_content, active_model):
        attachment = self.env["ir.attachment"].create(
            {
                "name": f"DEMEX_{sanction.employee_id.name}.pdf",
                "type": "binary",
                "datas": base64.b64encode(pdf_content),
                "res_model": active_model,
                "res_id": sanction.id,
                "mimetype": "application/pdf",
            }
        )

        self.attachment_ids = [(4, attachment.id)]

    def action_save_mail(self):
        """Save mail body on fields body sanction model"""
        sanction = self._get_sanction()
        notification_type = self.env.context.get("default_notification_type")
        if sanction.sanction_type_id and notification_type == "warning":
            sanction.warning_notification = self.body
        elif sanction.sanction_type_id and sanction.is_lay_off:
            if notification_type == "epl":
                sanction.epl_notification = self.body
            else:
                sanction.lay_off_notification = self.body

        return {"type": "ir.actions.act_window_close"}
