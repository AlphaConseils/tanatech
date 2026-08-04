# -*- coding: utf-8 -*-
"""
MCB — test checkout BOUTIQUE en USD (commande réelle via pricelist).

Contrairement à mcb_test_odoo_flow.py (transaction isolée), ce test part d'une
vraie sale.order créée avec la pricelist USD du website, donc il valide que le
storefront en USD aboutit bien à un paiement MCB.

Pré-requis : une pricelist USD définie par défaut pour le visiteur public
(voir la création de 'MCB USD Test' ci-dessous, à exécuter une fois).

Usage (depuis l'hôte) :
    cat mcb_test_shop_usd.py | docker exec -i odoo18 \
        odoo shell -c /etc/odoo/odoo.conf -d tanatech_mcb --no-http
"""
import re
import requests

website = env['website'].search([], limit=1)
pl = env['product.pricelist'].search([('name', '=', 'MCB USD Test')], limit=1)
prod = env['product.product'].search(
    [('product_tmpl_id.website_published', '=', True)], limit=1)
partner = env.ref('base.user_admin').partner_id
provider = env['payment.provider'].search([('code', '=', 'mcb')], limit=1)
pm = env.ref('payment.payment_method_card')

print('=' * 64)
print('TEST CHECKOUT BOUTIQUE EN USD (pricelist %s)' % pl.name)
print('=' * 64)

# 1) Commande boutique via la pricelist USD
so = env['sale.order'].create({
    'partner_id': partner.id,
    'pricelist_id': pl.id,
    'website_id': website.id,
    'order_line': [(0, 0, {'product_id': prod.id, 'product_uom_qty': 1})],
})
print('[1] Commande %s | produit "%s"' % (so.name, prod.name))
print('    devise = %s | total = %s %s' % (so.currency_id.name, so.amount_total, so.currency_id.name))

# 2) Transaction de paiement liée à la commande
tx = env['payment.transaction'].create({
    'provider_id': provider.id, 'payment_method_id': pm.id,
    'reference': so.name, 'amount': so.amount_total, 'currency_id': so.currency_id.id,
    'partner_id': partner.id, 'operation': 'online_redirect',
    'sale_order_ids': [(6, 0, so.ids)],
})
print('[2] Transaction %s | %s %s' % (tx.reference, tx.amount, tx.currency_id.name))

# 3) MCB proposé pour cette commande ?
compat = env['payment.provider']._get_compatible_providers(
    website.company_id.id, partner.id, so.amount_total, currency_id=so.currency_id.id)
print('[3] MCB proposé ? -> %s' % (provider in compat))

# 4) Session MCB + URL de redirection
rv = tx._get_specific_rendering_values(tx._get_processing_values())
url = rv.get('checkout_url')
print('[4] checkout_url = %s' % url)

# 5) Page MCB hébergée
r = requests.get(url, timeout=30)
title = re.search(r'<title>([^<]*)</title>', r.text)
ok = (r.status_code == 200
      and 'unable to complete' not in r.text.lower()
      and 'support code' not in r.text.lower())
print('[5] Page MCB : HTTP %s | title="%s" | saine=%s'
      % (r.status_code, title.group(1) if title else '?', ok))

print('=' * 64)
print('RESULTAT : %s' % ('OK ✅' if (url and ok and provider in compat) else 'ECHEC ❌'))
print('=' * 64)

# Ne rien laisser en base (la pricelist, elle, reste configurée)
env.cr.rollback()
