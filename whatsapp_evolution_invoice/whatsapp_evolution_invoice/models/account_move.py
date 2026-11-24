from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        invoices = posted.filtered(lambda m: m.move_type == "out_invoice")
        if invoices:
            templates = self.env["evo.whatsapp.template"].sudo().search(
                [("trigger", "=", "invoice_post"), ("model", "=", "account.move")]
            )
            for tmpl in templates:
                # Queued, not sent inline: confirm stays instant and the queue cron
                # applies random delays between messages to protect the number.
                tmpl._enqueue_for(invoices, dedupe=lambda m, t=tmpl: f"inv{t.id}:{m.id}")
        return posted

    def action_evo_send_whatsapp(self):
        if any(m.state != "posted" for m in self):
            raise UserError(_("Only posted invoices can be sent by WhatsApp."))
        template = self.env.ref(
            "whatsapp_evolution_invoice.evo_template_invoice", raise_if_not_found=False
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Send WhatsApp"),
            "res_model": "evo.whatsapp.composer",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "account.move",
                "active_ids": self.ids,
                "default_template_id": template.id if template and template.active else False,
            },
        }
