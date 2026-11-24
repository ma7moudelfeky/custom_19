from odoo import _, models
from odoo.exceptions import UserError


class FirmDocument(models.Model):
    _inherit = "firm.document"

    def _evo_expiry_template(self):
        tmpl = self.env.ref("whatsapp_evolution_invoice.evo_template_doc_expiry", raise_if_not_found=False)
        if not tmpl or not tmpl.active:
            tmpl = self.env["evo.whatsapp.template"].search(
                [("model", "=", "firm.document")], limit=1
            )
        if not tmpl:
            raise UserError(_("No active WhatsApp template for documents."))
        return tmpl

    def action_evo_whatsapp_alert(self):
        """Row button: send the expiry alert now to the document's Alert Users."""
        docs = self.filtered("alert_users_ids")
        if not docs:
            raise UserError(_("Add Alert Users (with mobile numbers) to the document first."))
        msgs = docs._evo_expiry_template()._enqueue_for(docs)
        missing = msgs.filtered(lambda m: not m.phone).mapped("recipient_name")
        message = _("%s WhatsApp alert(s) queued.", len(msgs))
        if missing:
            message += " " + _("No valid mobile for: %s", ", ".join(missing))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("WhatsApp"),
                "message": message,
                "type": "warning" if missing else "success",
            },
        }
