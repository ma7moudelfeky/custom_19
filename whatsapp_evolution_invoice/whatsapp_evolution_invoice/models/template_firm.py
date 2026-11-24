from datetime import timedelta

from odoo import fields, models


class EvoWhatsappTemplate(models.Model):
    _inherit = "evo.whatsapp.template"

    trigger = fields.Selection(
        selection_add=[("doc_expiry", "Document expiry (End Date - Alert Days)")],
        ondelete={"doc_expiry": "set default"},
    )

    def _run_trigger(self):
        if self.trigger != "doc_expiry" or self.model != "firm.document":
            return super()._run_trigger()
        today = fields.Date.context_today(self)
        # Only documents not yet expired (End Date >= today): no flood of old alerts.
        docs = self.env["firm.document"].sudo().search([
            ("last_update_date", ">=", today),
            ("state", "!=", "not"),
        ])
        due = docs.filtered(
            lambda d: d.last_update_date - timedelta(days=d.alert_days or 0) <= today
        )
        # Once per document per End Date (renewing the document re-arms the alert).
        self._enqueue_for(due, dedupe=lambda d: f"exp{self.id}:{d.id}:{d.last_update_date}")
