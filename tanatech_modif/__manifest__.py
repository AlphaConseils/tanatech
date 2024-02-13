# __manifest__.py

{
    'name': 'Gestion des autorisations de modification des articles',
    'version': '1.0',
    'summary': 'Ajoute une fonctionnalité de restriction de modification des articles',
    'description': 'Module Odoo pour restreindre la modification des articles en fonction d\'une case à cocher dans la sécurité',
    'author': 'nexources',
    'category': 'Uncategorized',
    'depends': ['base', 'product'],
    'data': [
    # 'security/security.xml',
    # 'views/product_template_form_view.xml'
    ],
    'installable': True,
    'application': True,
}
