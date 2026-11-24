from odoo import _, fields, models
from odoo.exceptions import UserError

from .evo_client import EvolutionClient, EvolutionError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    evo_api_url = fields.Char(
        string="Evolution API URL",
        config_parameter="evo_whatsapp.api_url",
        default="http://evolution_api:8080",
    )
    evo_api_key = fields.Char(string="API Key", config_parameter="evo_whatsapp.api_key")
    evo_instance = fields.Char(
        string="Instance Name", config_parameter="evo_whatsapp.instance", default="odoo"
    )
    evo_country_code = fields.Char(
        string="Default Country Code", config_parameter="evo_whatsapp.country_code", default="20"
    )
    evo_delay_min = fields.Integer(
        string="Min delay (sec)", config_parameter="evo_whatsapp.delay_min", default=8
    )
    evo_delay_max = fields.Integer(
        string="Max delay (sec)", config_parameter="evo_whatsapp.delay_max", default=20
    )
    evo_check_number = fields.Boolean(
        string="Skip numbers without WhatsApp", config_parameter="evo_whatsapp.check_number",
        default=True,
    )

    def set_values(self):
        if self.evo_delay_min < 1 or self.evo_delay_max < self.evo_delay_min:
            raise UserError(_("Delays must be >= 1 second and Max must be >= Min."))
        return super().set_values()

    def action_evo_test_connection(self):
        self.ensure_one()
        try:
            state = EvolutionClient(
                self.evo_api_url, self.evo_api_key, self.evo_instance
            ).connection_state()
        except EvolutionError as exc:
            raise UserError(str(exc)) from exc
        ok = state == "open"
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("WhatsApp connection"),
                "message": _("Instance '%(inst)s' state: %(state)s%(hint)s",
                             inst=self.evo_instance, state=state,
                             hint="" if ok else _(" — scan the QR code from Evolution Manager.")),
                "type": "success" if ok else "warning",
                "sticky": not ok,
            },
        }
