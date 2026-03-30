# -*- coding: utf-8 -*-
import logging

from odoo import _, models, SUPERUSER_ID

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process(self):
        """Extend native post-processing to cover two cases not handled by Odoo:

        1. Non-immediate payment (any provider, state 'pending', with sale orders):
           Odoo only sends the quotation by email. We confirm the order, create the
           invoice, and send it so the customer has the payment instructions.
           Bank reconciliation is done manually when the payment arrives.

        2. Direct invoice payment (MCB/MVola, state 'done', without sale order):
           Fallback for invoices linked directly to the transaction without a sale
           order (not handled by sale.automatic_invoice).
        """
        super()._post_process()
        for wire_tx in self.filtered(
            lambda tx: tx.state == "pending" and tx.sale_order_ids
        ):
            wire_tx._tanatech_process_wire_transfer()
        for done_tx in self.filtered(lambda tx: tx.state == "done"):
            done_tx._tanatech_send_invoice_email()

    def _tanatech_process_wire_transfer(self):
        """Confirm the sale order, create and send the invoice for non-immediate payments.

        Non-immediate payments (wire transfer, etc.) are set to 'pending' right away
        without real payment confirmation. We confirm the order and send the invoice
        so the customer has the payment instructions. The invoice is marked as paid
        later during manual bank reconciliation.
        """
        self.ensure_one()
        unconfirmed_orders = self.sale_order_ids.filtered(
            lambda so: so.state in ("draft", "sent")
        )
        if not unconfirmed_orders:
            return
        # Confirm without sending a separate confirmation email —
        # the invoice email below serves as the customer notification.
        unconfirmed_orders.action_confirm()
        # Create invoices for the confirmed orders.
        self._invoice_sale_orders()
        # Post any draft invoices.
        draft_invoices = self.invoice_ids.filtered(lambda inv: inv.state == "draft")
        if draft_invoices:
            draft_invoices.action_post()
        # Send the invoice email (is_move_sent prevents duplicates).
        self._send_invoice()
        _logger.info(
            "Non-immediate payment tx=%s: order(s) %s confirmed, invoice(s) %s created and sent",
            self.reference,
            unconfirmed_orders.mapped("name"),
            self.invoice_ids.mapped("name"),
        )

    def _tanatech_send_invoice_email(self):
        """Send posted invoices not yet emailed that are linked to this transaction.

        Fallback for direct invoice payments without a sale order.
        Payments linked to sale orders are already handled by sale._post_process().
        """
        self.ensure_one()
        invoices_to_send = self.invoice_ids.filtered(
            lambda inv: not inv.is_move_sent
            and inv.state == "posted"
            and inv._is_ready_to_be_sent()
        )
        if not invoices_to_send:
            return
        invoices_to_send.is_move_sent = True
        # sudo: account.move.send requires SUPERUSER to generate the PDF attachment
        self.env["account.move.send"].with_user(SUPERUSER_ID)._generate_and_send_invoices(
            invoices_to_send,
            allow_raising=False,
            allow_fallback_pdf=True,
        )
        _logger.info(
            "Invoice(s) %s sent by email after payment tx=%s",
            invoices_to_send.mapped("name"),
            self.reference,
        )
