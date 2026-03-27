# -*- coding: utf-8 -*-
import logging

from odoo import models, SUPERUSER_ID

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    def _post_process(self):
        """Envoie la facture par email après paiement pour les transactions directes.

        La méthode native sale._post_process() gère les paiements liés à des
        commandes (sale.automatic_invoice=True). Ce hook couvre les cas restants :
        factures liées directement à la transaction sans commande de vente.
        """
        super()._post_process()
        for tx in self.filtered(lambda t: t.state == "done"):
            tx._tanatech_send_invoice_email()

    def _tanatech_send_invoice_email(self):
        """Envoie les factures validées non encore envoyées liées à cette transaction."""
        self.ensure_one()
        invoice_to_send = self.invoice_ids.filtered(
            lambda inv: not inv.is_move_sent
            and inv.state == "posted"
            and inv._is_ready_to_be_sent()
        )
        if not invoice_to_send:
            return
        invoice_to_send.is_move_sent = True
        # sudo: account.move.send nécessite SUPERUSER pour la génération du PDF
        self.env["account.move.send"].with_user(SUPERUSER_ID)._generate_and_send_invoices(
            invoice_to_send,
            allow_raising=False,
            allow_fallback_pdf=True,
        )
        _logger.info(
            "Facture(s) %s envoyée(s) par email après paiement tx=%s",
            invoice_to_send.mapped("name"),
            self.reference,
        )
