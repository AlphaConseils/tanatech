/** @odoo-module **/
/**
 * MCB Payment Gateway — Module JS Odoo 18
 *
 * Odoo 18 utilise le système de modules ES natifs (@odoo-module).
 * La logique principale PaymentSession.configure() reste dans le template
 * QWeb car elle requiert des valeurs dynamiques serveur (session_id, etc.).
 *
 * Ce fichier exporte uniquement des utilitaires partagés si nécessaire.
 */

/**
 * Formate un montant pour l'affichage (ex: 1 234,56 MUR).
 * @param {number} amount
 * @param {string} currency  Code ISO (ex: "MUR", "EUR")
 * @returns {string}
 */
export function formatAmount(amount, currency) {
    return new Intl.NumberFormat('fr-FR', {
        style: 'currency',
        currency,
        minimumFractionDigits: 2,
    }).format(amount);
}
