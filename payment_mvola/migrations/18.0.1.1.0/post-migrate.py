from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if version is None:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    module = env["ir.module.module"].search([("name", "=", "payment_mvola")], limit=1)
    if not module:
        return
    provider = env["payment.provider"].search([("code", "=", "mvola")], limit=1)
    if provider and not provider.module_id:
        provider.module_id = module
