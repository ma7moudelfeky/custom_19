{
    'name': 'WhatsApp Invoice via Evolution API',
    'version': '19.0.1.1.0',
    'summary': 'Send posted customer invoices as PDF over WhatsApp using a self-hosted Evolution API',
    'category': 'Accounting',
    'author': 'Mahmoud Elfeky',
    'license': 'LGPL-3',
    'depends': ['account'],
    'data': [
        'data/ir_cron.xml',
        'views/res_config_settings_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
}
