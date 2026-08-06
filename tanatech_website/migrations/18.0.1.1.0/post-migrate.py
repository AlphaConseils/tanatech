from odoo import api, SUPERUSER_ID

# Message affiche au client sur la page de confirmation de commande (et sur
# /payment/status) lorsque sa transaction reste "en attente", c'est-a-dire pour
# tout paiement non immediat : virement bancaire aujourd'hui, en attendant que
# les API MVola / MCB soient disponibles.
#
# Pourquoi un script de migration et non un fichier de donnees : l'enregistrement
# payment.payment_provider_transfer porte ir_model_data.noupdate = True (pose par
# le module `payment`), et models.py::_load_records ignore toute mise a jour d'un
# tel enregistrement (`if not (update and d_noupdate)`). Un <record> dans data/
# serait donc purement sans effet sur une base ou le module est deja installe.

EN_1 = "Your order has been registered and is now being handled by our sales team."
EN_2 = (
    "Online payment is not available yet: a sales representative will contact you"
    " shortly to confirm your order and arrange the payment."
)
FR_1 = (
    "Votre commande a bien été enregistrée et est prise en charge par notre équipe"
    " commerciale."
)
FR_2 = (
    "Le paiement en ligne n'est pas encore disponible : un conseiller vous recontactera"
    " prochainement pour confirmer votre commande et convenir du règlement."
)

# Marqueurs des messages poses automatiquement (defaut Odoo, ou bloc "coordonnees
# bancaires" genere par payment_custom). Leur presence signifie que personne n'a
# saisi de texte metier : on peut ecraser sans rien perdre.
AUTO_MARKERS = (
    "transfer details",
    "waiting for approval",
    "en attente d'approbation",
    "en attente de validation",
)


def migrate(cr, version):
    if version is None:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    provider = env.ref("payment.payment_provider_transfer", raise_if_not_found=False)
    if not provider:
        return

    current = provider.with_context(lang="en_US").pending_msg or ""
    # Ne jamais ecraser un texte saisi par l'equipe metier en back-office.
    if current and not any(marker in current for marker in AUTO_MARKERS):
        return

    provider.with_context(lang="en_US").pending_msg = f"<p>{EN_1}</p><p>{EN_2}</p>"
    provider.update_field_translations(
        "pending_msg", {"fr_FR": {EN_1: FR_1, EN_2: FR_2}}
    )
