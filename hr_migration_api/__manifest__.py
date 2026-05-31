{
    'name': 'HR Migration API',
    'version': '18.0.1.0.0',
    'summary': 'API RPC pour restauration des données RH supprimées',
    'description': """
        Expose des méthodes XML-RPC permettant au script de migration de :
        - Créer des enregistrements RH en forçant le state (leave, payslip, expense…)
        - Restaurer les messages du chatter avec l'auteur et la date d'origine
        - Restaurer les pièces jointes
        - Restaurer les lettrages comptables (account.partial.reconcile)
        À désinstaller une fois la migration terminée.
    """,
    'author': 'NEX',
    'category': 'Human Resources',
    'license': 'LGPL-3',
    'depends': ['hr', 'hr_holidays', 'hr_payroll', 'hr_expense', 'account', 'mail'],
    'data': [
        'security/ir.model.access.csv',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
