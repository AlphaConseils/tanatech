# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    website_customer_confirmed = fields.Boolean(
        string="Confirmed by Customer (Website)",
        copy=False,
        readonly=True,
        help="Checked when the order was confirmed by the customer from the "
        "website (eCommerce payment or signature on the portal).",
    )

    def action_confirm(self):
        res = super().action_confirm()
        web_orders = self.filtered(
            lambda so: so.state == "sale"
            and not so.website_customer_confirmed
            and so._is_confirmed_from_website()
        )
        if web_orders:
            web_orders = web_orders.sudo()
            web_orders.website_customer_confirmed = True
            web_orders._schedule_website_confirmation_activities()
        return res

    def _is_confirmed_from_website(self):
        self.ensure_one()
        # eCommerce order, or confirmation done by the customer themselves
        # (portal/public user: online signature or payment of a quotation).
        return bool(self.website_id) or not self.env.user._is_internal()

    def _schedule_website_confirmation_activities(self):
        for order in self:
            company = order.company_id

            # Quotation → sales team
            sale_users = (
                company.website_confirm_sale_activity_user_ids
                or order.user_id
                or order.team_id.user_id
            )
            order._schedule_web_activity(
                sale_users,
                _("Sales follow-up — web order confirmed"),
                _(
                    "Customer %(customer)s confirmed order %(order)s on the "
                    "website. Please follow up on this sale.",
                    customer=order.partner_id.display_name,
                    order=order.name,
                ),
            )

            # Delivery order(s) → procurement team
            for picking in order.picking_ids:
                delivery_users = (
                    company.website_confirm_delivery_activity_user_ids
                    or picking.user_id
                    or order.user_id
                )
                picking._schedule_web_activity(
                    delivery_users,
                    _("Prepare delivery — web order %s", order.name),
                    _(
                        "Web order %(order)s from customer %(customer)s has "
                        "been confirmed. Please process delivery order %(picking)s.",
                        order=order.name,
                        customer=order.partner_id.display_name,
                        picking=picking.name,
                    ),
                )

    def _create_invoices(self, grouped=False, final=False, date=None):
        # Invoice → finance team, as soon as an invoice is generated
        # from a web order confirmed by the customer.
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves.sudo().filtered(lambda m: m.move_type == "out_invoice"):
            orders = move.line_ids.sale_line_ids.order_id.filtered(
                "website_customer_confirmed"
            )
            if not orders:
                continue
            invoice_users = (
                move.company_id.website_confirm_invoice_activity_user_ids
                or move.invoice_user_id
                or orders[:1].user_id
            )
            move._schedule_web_activity(
                invoice_users,
                _("Invoicing follow-up — web order %s", ", ".join(orders.mapped("name"))),
                _(
                    "Invoice %(move)s has been generated for web order "
                    "%(order)s of customer %(customer)s. Please follow up on "
                    "the invoicing.",
                    move=move.name or move.payment_reference or "",
                    order=", ".join(orders.mapped("name")),
                    customer=move.partner_id.display_name,
                ),
            )
        return moves


class MailActivityMixin(models.AbstractModel):
    _inherit = "mail.activity.mixin"

    def _schedule_web_activity(self, users, summary, note):
        """Schedule a "To-Do" activity on each record for each of the given
        users (non-internal users are ignored)."""
        internal_users = users.filtered(lambda u: u.active and u._is_internal())
        if not internal_users:
            _logger.warning(
                "tanatech_website_sale: no internal user to assign the "
                "activity '%s' on %s; activity not created.",
                summary,
                self,
            )
            return
        for record in self:
            for user in internal_users:
                record.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=user.id,
                    summary=summary,
                    note=note,
                )
