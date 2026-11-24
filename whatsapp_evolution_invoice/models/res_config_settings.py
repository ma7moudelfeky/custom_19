from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    evo_api_url = fields.Char(
        string='Evolution API URL',
        config_parameter='whatsapp_evolution.api_url',
        default='http://evolution_api:8080',
    )
    evo_api_key = fields.Char(string='API Key', config_parameter='whatsapp_evolution.api_key')
    evo_instance = fields.Char(string='Instance Name', config_parameter='whatsapp_evolution.instance')
    evo_auto_send = fields.Boolean(
        string='Send on Invoice Confirm',
        config_parameter='whatsapp_evolution.auto_send',
    )
    evo_delay_min = fields.Integer(
        string='Min Delay (s)', config_parameter='whatsapp_evolution.delay_min', default=8,
    )
    evo_delay_max = fields.Integer(
        string='Max Delay (s)', config_parameter='whatsapp_evolution.delay_max', default=20,
    )
    evo_batch_size = fields.Integer(
        string='Messages per Run', config_parameter='whatsapp_evolution.batch_size', default=5,
    )
