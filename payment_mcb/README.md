# payment_mcb — Module Odoo 18 pour MCB Payment Gateway (Hosted Session)

## Architecture

```
payment_mcb/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── payment_provider.py     ← Credentials + appels API MCB
│   └── payment_transaction.py  ← Gestion états transaction + remboursements
├── controllers/
│   └── main.py                 ← Routes HTTP : create_session, process_payment
├── views/
│   ├── payment_mcb_templates.xml   ← Formulaire de paiement (HTML + iframes MCB)
│   └── payment_provider_views.xml  ← Champs credentials dans le back-office
├── static/src/
│   ├── js/payment_form.js      ← Logique JS (PaymentSession.configure, callbacks)
│   └── css/payment_form.css    ← Styles du formulaire
└── data/
    └── payment_provider_data.xml   ← Enregistrement initial du provider
```

## Flux de paiement (Hosted Session)

```
[Client Odoo Checkout]
       │
       ▼
1. GET /shop/payment  →  Odoo appelle _get_specific_rendering_values()
                         → POST MCB /session                (Create Session)
                         → PUT  MCB /session/{id}           (Update with amount/currency)
                         → Rendu du template avec session_id + session_js_url
       │
       ▼
2. Page chargée  →  <script src="session.js"> chargé depuis MCB
                 →  PaymentSession.configure({ session, fields, callbacks })
                 →  MCB remplace les <input> par des iframes sécurisées

       │
       ▼
3. Utilisateur saisit ses données carte dans les iframes MCB
       │
       ▼
4. Clic "Payer"  →  PaymentSession.updateSessionFromForm('card')
                    → MCB JS envoie les données directement à MCB Gateway
                    → Callback formSessionUpdate({ status: 'ok', session.id })
       │
       ▼
5. Callback ok  →  POST /payment/mcb/process_payment
                   → GET  MCB /session/{id}              (Retrieve Session – vérification)
                   → PUT  MCB /order/{ref}/transaction/{ref}  (PAY operation)
                   → _process_notification_data() → set_done() / set_error()
       │
       ▼
6. Redirect  →  /payment/status
```

## Configuration

1. Installer le module dans Odoo
2. Aller dans **Comptabilité > Configuration > Moyens de paiement**
3. Activer **MCB Payment Gateway**
4. Renseigner :
   - **Merchant ID** : votre ID commerçant MCB (ex : `TESTMERCHANT`)
   - **API Password** : votre mot de passe API MCB
5. Passer en mode **Test** pour les tests, puis **Production** pour la mise en ligne

## Prérequis

- Odoo 18 (compatible 16 avec ajustements mineurs)
- Compte commerçant MCB Payment Gateway actif
- API v18 ou supérieure activée sur votre profil (la v72 est utilisée ici)
- Module `payment` + `website_sale`

## Sécurité & PCI DSS

Les données de carte (numéro, CVV, expiration) **ne transitent jamais** par le serveur Odoo.
Elles sont capturées directement par les iframes hébergées par MCB Gateway.
Ce module est donc **hors scope PCI DSS** pour le commerçant.
