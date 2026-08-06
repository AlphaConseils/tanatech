# -*- coding: utf-8 -*-
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

# Supprime les personnalisations d'assets faites via l'editeur de code du site
# web (Website > editeur HTML/SCSS) sur les fichiers de tanatech_website.
#
# Ces personnalisations sont stockees en base (ir.attachment url
# "/_custom/<bundle>/<chemin du fichier>" + ir.asset "replace") et ecrasent le
# fichier du depot a chaque generation du bundle : les correctifs pousses par
# git sur ces fichiers restent alors sans effet. Une vieille copie de
# web_loging.scss servait notamment d'anciennes regles du carrousel "Nouveaux
# produits" (fleches en position absolue qui chevauchent la section suivante).
# Le depot est la seule source de verite pour ces fichiers : on purge.


def migrate(cr, version):
    if version is None:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    attachments = env["ir.attachment"].search(
        [("url", "like", "/_custom/%/tanatech_website/%")]
    )
    assets = env["ir.asset"].search(
        [("path", "like", "_custom/%/tanatech_website/%")]
    )

    if not attachments and not assets:
        _logger.info("tanatech_website: aucun asset personnalise a purger.")
        return

    _logger.warning(
        "tanatech_website: purge de %d attachment(s) et %d ir.asset "
        "personnalises qui masquaient les fichiers du depot : %s",
        len(attachments),
        len(assets),
        ", ".join(attachments.mapped("url") + assets.mapped("path")),
    )
    attachments.unlink()
    assets.unlink()
