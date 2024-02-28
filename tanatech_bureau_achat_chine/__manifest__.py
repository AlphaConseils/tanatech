# -*- coding: utf-8 -*-
{
    'name': "Bureau d'achat Chine",
    'summary': "Limit access to Purchase Orders for Bureau d'achat Chine",
    'version': '14.0.1.0.0',
    'depends': ['purchase'],
    'data': [
        'security/bureau_achat_chine_security.xml',
        'security/ir.model.access.csv',
        'data/bureau_achat_chine_data.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
