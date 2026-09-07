# -*- coding: utf-8 -*-
"""
MCB — test bout-en-bout DU CHEMIN ODOO (pas seulement l'API brute).

Reproduit fidèlement ce que fait le checkout web, mais en pilotant directement
les méthodes Odoo réelles, contre l'API MCB réelle :

  1. crée une payment.transaction (devise/montant paramétrables)
  2. vérifie que MCB est proposé pour cette devise (_get_compatible_providers)
  3. appelle _get_specific_rendering_values -> crée la session MCB (INITIATE_CHECKOUT)
  4. rend le template de redirection (ce que reçoit le navigateur du client)
  5. récupère la page MCB hébergée et vérifie qu'elle est saine
  6. rollback : aucune transaction de test laissée en base

Usage (depuis l'hôte) :
    cat mcb_test_odoo_flow.py | docker exec -i odoo18 \
        odoo shell -c /etc/odoo/odoo.conf -d tanatech_mcb --no-http

Paramètres : changer CURRENCY / AMOUNT ci-dessous.
"""
import datetime
import re
import requests

CURRENCY = 'USD'   # devise supportée par MCB : USD / MUR / EUR
AMOUNT = 50.0

provider = env['payment.provider'].search([('code', '=', 'mcb')], limit=1)
cur = env['res.currency'].with_context(active_test=False).search(
    [('name', '=', CURRENCY)], limit=1)
pm = env.ref('payment.payment_method_card')
partner = env.ref('base.user_admin').partner_id
company = provider.company_id or env.company
ref = 'E2E-%s-%s' % (CURRENCY, datetime.datetime.now().strftime('%H%M%S'))

print('=' * 64)
print('MCB E2E (chemin Odoo) — %s %s — provider state=%s' % (AMOUNT, CURRENCY, provider.state))
print('=' * 64)

# 2) MCB proposé pour cette devise ?
compat = env['payment.provider']._get_compatible_providers(
    company.id, partner.id, AMOUNT, currency_id=cur.id)
print('[1] MCB proposé pour %s ......... %s' % (CURRENCY, provider in compat))

# 1) transaction
tx = env['payment.transaction'].create({
    'provider_id': provider.id,
    'payment_method_id': pm.id,
    'reference': ref,
    'amount': AMOUNT,
    'currency_id': cur.id,
    'partner_id': partner.id,
    'operation': 'online_redirect',
})
print('[2] Transaction créée ........... %s (%s %s)' % (tx.reference, tx.amount, cur.name))

# 3) session MCB
pv = tx._get_processing_values()
rv = tx._get_specific_rendering_values(pv)
url = rv.get('checkout_url')
print('[3] Session MCB ................. order_id=%s indicator=%s'
      % (tx.mcb_order_id, tx.mcb_success_indicator))
print('    checkout_url ............... %s' % url)

# 4) form de redirection rendu
html = str(env['ir.qweb']._render(provider.redirect_form_view_id.id, dict(rv)))
form = re.search(r'<form[^>]*>', html)
print('[4] Form redirection ........... %s' % (form.group(0) if form else 'INTROUVABLE'))

# 5) page MCB hébergée
resp = requests.get(url, timeout=30)
title = re.search(r'<title>([^<]*)</title>', resp.text)
page_ok = (resp.status_code == 200
           and 'unable to complete' not in resp.text.lower()
           and 'support code' not in resp.text.lower())
print('[5] Page MCB ................... HTTP %s | title="%s" | saine=%s'
      % (resp.status_code, title.group(1) if title else '?', page_ok))

print('=' * 64)
print('RESULTAT : %s' % ('OK ✅' if (url and page_ok) else 'ECHEC ❌'))
print('=' * 64)

# 6) ne rien laisser en base
env.cr.rollback()
