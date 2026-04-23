from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if version is None:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    provider = env["payment.provider"].search([("code", "=", "mcb")], limit=1)
    if not provider:
        return
    redirect_view = env.ref("payment_mcb.payment_form", raise_if_not_found=False)
    if redirect_view and not provider.redirect_form_view_id:
        provider.redirect_form_view_id = redirect_view
    if provider.inline_form_view_id:
        provider.inline_form_view_id = False
