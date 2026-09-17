import re
import unicodedata

from odoo import api, fields, models

# Société dont les contrats ne perçoivent pas de prime de mission (règle D).
#
# La migration 18.0.1.2.23 porte sa propre copie de ce nom : un script de
# migration doit rester autonome, il tourne sur une base dont le code Python
# n'est pas forcément celui d'aujourd'hui. Les deux se comparent sur la même
# forme normalisée.
MISSION_INELIGIBLE_COMPANY = "MASONTSIKA"


def _normalize(label):
    """ Clé de comparaison insensible à la casse, aux accents et à la
    ponctuation : « Masontsika », « MASONTSIKA » et « Masontsika S.A.R.L » ne
    doivent pas se comporter différemment sur un simple écart de saisie. """
    text = unicodedata.normalize("NFKD", label or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-zA-Z]+", " ", text).strip().lower()


class HrContract(models.Model):
    _inherit = "hr.contract"

    @api.model
    def _default_tanatech_mission_eligible(self):
        """ Un contrat créé chez MASONTSIKA naît NON éligible, ailleurs éligible.

        Sans cela, chaque embauche chez MASONTSIKA repartirait éligible et il
        faudrait penser à décocher : la valeur posée par la migration ne vaut
        que pour le parc existant, pas pour la suite.

        La société est lue dans le contexte avant de retomber sur celle de
        l'utilisateur : à la création depuis la fiche salarié, c'est
        default_company_id qui porte la bonne, et elle n'est pas
        nécessairement celle de l'utilisateur en multi-société.
        """
        company = self.env['res.company'].browse(
            self.env.context.get('default_company_id')) or self.env.company
        return _normalize(company.name) != _normalize(MISSION_INELIGIBLE_COMPANY)

    # Éligibilité à la prime de mission (règle D, arbitrage Patty).
    #
    # La prime MISS est versée sur les structures NA sans aucune condition
    # d'éligibilité : tout salarié ayant une entrée de mission la touche. Le
    # client veut pouvoir en exclure des personnes : toute la société
    # MASONTSIKA, puis une liste de responsables TANATECH qu'il cochera à la
    # main.
    #
    # Le défaut suit la société du contrat. La valeur initiale du parc est posée
    # une seule fois par la migration 18.0.1.2.23, qui se garde de repasser
    # derrière les décochages manuels du client.
    #
    # Le contrat NA étant une copie du contrat déclaré, la case est recopiée à
    # la création, le défaut ne s'applique donc pas à lui ; en revanche les
    # écritures ultérieures ne sont PAS propagées
    # (tanatech_hr_contract.HrContract.write ne propage qu'une liste fermée de
    # champs). C'est pourquoi hr.payslip._tanatech_mission_eligible regarde les
    # DEUX contrats : décocher le contrat déclaré suffit.
    tanatech_mission_eligible = fields.Boolean(
        string="Éligible à la prime de mission",
        default=lambda self: self._default_tanatech_mission_eligible(),
        tracking=True,
        help="Décoché, ce contrat ne perçoit aucune prime de mission. "
             "La case du contrat déclaré vaut aussi pour le contrat NA "
             "correspondant : il suffit de décocher le contrat déclaré.",
    )

    def generate_work_entries(self, date_start, date_stop, force=False):
        work_entries = super().generate_work_entries(date_start, date_stop, force)
        work_entries.auto_update_overtime_work_entry_type()
        return work_entries
