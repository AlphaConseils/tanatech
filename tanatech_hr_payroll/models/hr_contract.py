from odoo import fields, models


class HrContract(models.Model):
    _inherit = "hr.contract"

    # Éligibilité à la prime de mission (règle D, arbitrage Patty).
    #
    # La prime MISS est versée sur les structures NA sans aucune condition
    # d'éligibilité : tout salarié ayant une entrée de mission la touche. Le
    # client veut pouvoir en exclure des personnes — toute la société
    # MASONTSIKA, puis une liste de responsables TANATECH qu'il cochera à la
    # main.
    #
    # Le défaut est True : un contrat créé demain est éligible, l'exclusion est
    # un acte explicite. La valeur initiale du parc est posée une seule fois par
    # la migration 18.0.1.2.23 (False sur MASONTSIKA, True ailleurs), qui se
    # garde de repasser derrière les décochages manuels du client.
    #
    # Le contrat NA étant une copie du contrat déclaré, la case est recopiée à
    # la création ; en revanche les écritures ultérieures ne sont PAS propagées
    # (tanatech_hr_contract.HrContract.write ne propage qu'une liste fermée de
    # champs). C'est pourquoi hr.payslip._tanatech_mission_eligible regarde les
    # DEUX contrats : décocher le contrat déclaré suffit.
    tanatech_mission_eligible = fields.Boolean(
        string="Éligible à la prime de mission",
        default=True,
        tracking=True,
        help="Décoché, ce contrat ne perçoit aucune prime de mission. "
             "La case du contrat déclaré vaut aussi pour le contrat NA "
             "correspondant : il suffit de décocher le contrat déclaré.",
    )

    def generate_work_entries(self, date_start, date_stop, force=False):
        work_entries = super().generate_work_entries(date_start, date_stop, force)
        work_entries.auto_update_overtime_work_entry_type()
        return work_entries
