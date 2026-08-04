#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCB Payment Gateway — script de test minimal (version simplifiée).

Reproduit, HORS Odoo, l'unique appel API utilise en production par le module
payment_mcb : CREATE_CHECKOUT_SESSION (mode Hosted Checkout).

Usage :
    pip install requests
    python3 mcb_test_session.py

Renseigner MERCHANT_ID / API_PASSWORD ci-dessous (identifiants de TEST).
"""
import os
import json
import requests
from requests.auth import HTTPBasicAuth

# ── Identifiants de TEST fournis par MCB ───────────────────────────────────
# Renseigner ici, OU passer par variables d'environnement :
#   MCB_MERCHANT_ID=xxx MCB_API_PASSWORD=yyy python3 mcb_test_session.py
MERCHANT_ID  = os.environ.get("MCB_MERCHANT_ID",  "VOTRE_MERCHANT_ID")
API_PASSWORD = os.environ.get("MCB_API_PASSWORD", "VOTRE_API_PASSWORD")

API_VERSION = 72
BASE_URL = f"https://mcb.gateway.mastercard.com/api/rest/version/{API_VERSION}/merchant/{MERCHANT_ID}"
AUTH = HTTPBasicAuth(f"merchant.{MERCHANT_ID}", API_PASSWORD)

# ── Données de la commande de test ─────────────────────────────────────────
ORDER_ID    = "TEST-ORDER-001"
AMOUNT      = 100.00
CURRENCY    = "MUR"
RETURN_URL  = "https://example.com/payment/mcb/return?order_id=" + ORDER_ID


def create_checkout_session():
    url = f"{BASE_URL}/session"
    payload = {
        # MCB gateway v72 expects INITIATE_CHECKOUT; the legacy name
        # CREATE_CHECKOUT_SESSION is rejected ("Unexpected parameter").
        "apiOperation": "INITIATE_CHECKOUT",
        "interaction": {
            "operation": "PURCHASE",
            "returnUrl": RETURN_URL,
        },
        "order": {
            "amount": AMOUNT,
            "currency": CURRENCY,
            "id": ORDER_ID,
        },
    }

    print("=" * 70)
    print("REQUETE  ->  POST", url)
    print(json.dumps(payload, indent=2))
    print("=" * 70)

    resp = requests.post(url, json=payload, auth=AUTH, timeout=30)

    print("REPONSE  <-  HTTP", resp.status_code)
    try:
        data = resp.json()
        print(json.dumps(data, indent=2))
    except ValueError:
        print(resp.text)
        return

    print("=" * 70)
    if data.get("result") == "SUCCESS":
        session_id = data.get("session", {}).get("id")
        indicator = data.get("successIndicator", "")
        checkout_url = f"https://mcb.gateway.mastercard.com/checkout/pay/{session_id}"
        print("SESSION ID        :", session_id)
        print("SUCCESS INDICATOR :", indicator)
        print("URL DE PAIEMENT   :", checkout_url)
    else:
        print("Echec de creation de session :", data.get("result"))
    print("=" * 70)


if __name__ == "__main__":
    create_checkout_session()
