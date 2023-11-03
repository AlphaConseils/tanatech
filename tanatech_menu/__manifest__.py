# __manifest__.py
{
    'name': "Tanatech Menu",
    'summary': "menu personnaliser",
    'version': '1.0',
    'category': 'Uncategorized',
    'author': "Nexources",
    'depends': ['point_of_sale'],
    'data': [
       # WIZARD
       'wizard/pos_report_wizard_views.xml',
    
        # VIEWS
       'views/menu.xml',
       
        # REPORT
       'report/report_saledetails_bis.xml',
       'report/ir_actions_report.xml',

    ],
    'installable': True,
    'application': True,
}
