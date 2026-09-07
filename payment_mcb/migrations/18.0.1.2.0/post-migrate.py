from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if version is None:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    provider = env["payment.provider"].search([("code", "=", "mcb")], limit=1)
    card_method = env.ref("payment.payment_method_card", raise_if_not_found=False)
    if provider and card_method and card_method not in provider.payment_method_ids:
        provider.payment_method_ids = [(4, card_method.id)]
