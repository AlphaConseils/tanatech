# -*- coding: utf-8 -*-

from odoo import models


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    def _get_overlapping_contracts(self, contract_states=None):
        """ Les contrats NA ne comptent pas parmi les contrats qui « chevauchent »
        un congé.

        Un NA est le miroir de son contrat déclaré : mêmes dates, même horaire,
        ce dernier lui étant recopié par tanatech_hr_contract.HrContract.write.
        Le compter à part posait deux problèmes dans hr_holidays_contract :
        - hr.contract.write trie ces contrats par état avec une table qui ne
          connaît pas 'open_not_declared' : changer l'horaire d'un contrat en
          cours plantait (KeyError) dès que le salarié avait un congé ;
        - _check_contracts refuse un congé couvrant des contrats d'horaires
          différents : entre l'écriture du contrat déclaré et la recopie de
          l'horaire sur son NA, les deux diffèrent un instant.
        """
        return super()._get_overlapping_contracts(contract_states).filtered(
            lambda c: c.contract_category != 'not_declared')
