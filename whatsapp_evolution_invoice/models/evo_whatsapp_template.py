import logging

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

RECIPIENT_TYPES = [
    ("record", "Record contact (customer / lead phone)"),
    ("users", "Users of a field (e.g. Alert Users)"),
    ("fixed", "Fixed numbers"),
]


class EvoWhatsappTemplate(models.Model):
    _name = "evo.whatsapp.template"
    _inherit = ["mail.render.mixin"]
    _description = "WhatsApp Template"
    _order = "model, sequence, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    model_id = fields.Many2one(
        "ir.model", string="Applies to", required=True, ondelete="cascade",
        domain=[("transient", "=", False)],
    )
    model = fields.Char(related="model_id.model", store=True, index=True)
    body = fields.Text(
        required=True, render_engine="inline_template",
        help="Use {{ object.field }} placeholders, e.g. {{ object.partner_id.name }}",
    )
    attachment_ids = fields.Many2many(
        "ir.attachment", "evo_whatsapp_template_attachment_rel", "template_id", "attachment_id",
        string="Fixed Attachments",
    )
    report_id = fields.Many2one(
        "ir.actions.report", string="Attach PDF Report",
        domain="[('model', '=', model), ('report_type', '=', 'qweb-pdf')]",
    )
    recipient_type = fields.Selection(RECIPIENT_TYPES, default="record", required=True)
    user_field_id = fields.Many2one(
        "ir.model.fields", string="Users Field", ondelete="set null",
        domain="[('model_id', '=', model_id), ('relation', '=', 'res.users'),"
               " ('ttype', 'in', ('many2one', 'many2many'))]",
    )
    fixed_numbers = fields.Char(help="Comma separated, e.g. 01001234567, 01112223334")
    trigger = fields.Selection(
        [("manual", "Manual only"), ("scheduled", "Scheduled (every hour, by filter)")],
        default="manual", required=True,
    )
    filter_domain = fields.Char(
        string="Filter", default="[]",
        help="Scheduled: records matching this filter receive the message once.",
    )
    message_count = fields.Integer(compute="_compute_message_count")

    @api.depends("model")
    def _compute_render_model(self):
        for tmpl in self:
            tmpl.render_model = tmpl.model

    def _compute_message_count(self):
        data = self.env["evo.whatsapp.message"]._read_group(
            [("template_id", "in", self.ids)], ["template_id"], ["__count"]
        )
        counts = {tmpl.id: count for tmpl, count in data}
        for tmpl in self:
            tmpl.message_count = counts.get(tmpl.id, 0)

    @api.constrains("recipient_type", "user_field_id", "fixed_numbers")
    def _check_recipients(self):
        for tmpl in self:
            if tmpl.recipient_type == "users" and not tmpl.user_field_id:
                raise ValidationError(_("Choose the users field for template '%s'.", tmpl.name))
            if tmpl.recipient_type == "fixed" and not tmpl.fixed_numbers:
                raise ValidationError(_("Enter the fixed numbers for template '%s'.", tmpl.name))

    # ----------------------------------------------------------------- render
    def _render_bodies(self, records):
        """{res_id: text}. Template bodies are vetted on save (mail.render.mixin),
        so they are rendered as superuser to work from crons/automatic triggers."""
        self.ensure_one()
        return self.sudo()._render_template(
            self.body, self.model, records.ids, engine="inline_template"
        )

    def _enqueue_for(self, records, dedupe=None):
        """Queue this template for the given records. ``dedupe(record) -> key|None``."""
        self.ensure_one()
        if not records:
            return self.env["evo.whatsapp.message"]
        return self.env["evo.whatsapp.message"].sudo()._evo_enqueue(
            records,
            bodies=self._render_bodies(records),
            template=self,
            attachments=self.attachment_ids,
            report=self.report_id,
            recipient_type=self.recipient_type,
            user_field=self.user_field_id.name,
            fixed_numbers=self.fixed_numbers,
            dedupe=dedupe,
        )

    # --------------------------------------------------------------- triggers
    def _run_trigger(self):
        """Hook: bridges extend for their own trigger values."""
        self.ensure_one()
        if self.trigger == "scheduled":
            domain = safe_eval(self.filter_domain or "[]")
            records = self.env[self.model].sudo().search(domain, limit=500)
            self._enqueue_for(records, dedupe=lambda r: f"sch{self.id}:{r.id}")

    @api.model
    def _cron_run_triggers(self):
        for tmpl in self.sudo().search([("trigger", "!=", "manual")]):
            try:
                with self.env.cr.savepoint():
                    tmpl._run_trigger()
            except Exception:
                _logger.exception("WhatsApp template trigger failed: %s", tmpl.name)

    def action_view_messages(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Messages"),
            "res_model": "evo.whatsapp.message",
            "view_mode": "list,form",
            "domain": [("template_id", "=", self.id)],
        }
