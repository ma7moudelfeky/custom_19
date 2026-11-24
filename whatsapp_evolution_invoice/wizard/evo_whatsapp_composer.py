import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.evo_whatsapp_template import RECIPIENT_TYPES


class EvoWhatsappComposer(models.TransientModel):
    _name = "evo.whatsapp.composer"
    _description = "Send WhatsApp"

    res_model = fields.Char(required=True)
    res_ids = fields.Text(required=True, help="JSON list of record ids")
    record_count = fields.Integer(compute="_compute_record_count")
    template_id = fields.Many2one(
        "evo.whatsapp.template", domain="[('model', '=', res_model)]"
    )
    body = fields.Text(string="Message")
    attachment_ids = fields.Many2many(
        "ir.attachment", "evo_whatsapp_composer_attachment_rel", "composer_id", "attachment_id",
        string="Attachments",
    )
    report_id = fields.Many2one(
        "ir.actions.report", string="Attach PDF Report",
        domain="[('model', '=', res_model), ('report_type', '=', 'qweb-pdf')]",
    )
    recipient_type = fields.Selection(RECIPIENT_TYPES, default="record", required=True)
    user_field_id = fields.Many2one(
        "ir.model.fields", string="Users Field",
        domain="[('model', '=', res_model), ('relation', '=', 'res.users'),"
               " ('ttype', 'in', ('many2one', 'many2many'))]",
    )
    fixed_numbers = fields.Char()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        model = res.get("res_model") or ctx.get("active_model")
        ids = ctx.get("active_ids") or ([ctx["active_id"]] if ctx.get("active_id") else [])
        if model and not res.get("res_model"):
            res["res_model"] = model
        if ids and not res.get("res_ids"):
            res["res_ids"] = json.dumps(ids)
        Template = self.env["evo.whatsapp.template"]
        tmpl = Template.browse(res["template_id"]) if res.get("template_id") else Template
        if model and not tmpl:
            tmpl = Template.search([("model", "=", model)], limit=1)
        if tmpl:
            # onchange does not run on default values: pre-fill from the template here
            res.update({
                "template_id": tmpl.id,
                "body": res.get("body") or tmpl.body,
                "report_id": tmpl.report_id.id,
                "recipient_type": tmpl.recipient_type,
                "user_field_id": tmpl.user_field_id.id,
                "fixed_numbers": tmpl.fixed_numbers,
                "attachment_ids": [(6, 0, tmpl.attachment_ids.ids)],
            })
        return res

    @api.depends("res_ids")
    def _compute_record_count(self):
        for wiz in self:
            wiz.record_count = len(json.loads(wiz.res_ids or "[]"))

    @api.onchange("template_id")
    def _onchange_template_id(self):
        tmpl = self.template_id
        if tmpl:
            self.body = tmpl.body
            self.report_id = tmpl.report_id
            self.recipient_type = tmpl.recipient_type
            self.user_field_id = tmpl.user_field_id
            self.fixed_numbers = tmpl.fixed_numbers
            self.attachment_ids = [(6, 0, tmpl.attachment_ids.ids)]

    def action_send(self):
        self.ensure_one()
        if not self.body and not self.attachment_ids and not self.report_id:
            raise UserError(_("Write a message or add an attachment."))
        if self.recipient_type == "users" and not self.user_field_id:
            raise UserError(_("Choose the users field."))
        records = self.env[self.res_model].browse(json.loads(self.res_ids or "[]")).exists()
        if not records:
            raise UserError(_("No records selected."))
        records.check_access("read")
        # Rendered as the current user: users without the template-editor right
        # only get simple {{ object.field }} placeholders (mail.render.mixin rule).
        bodies = self.env["evo.whatsapp.template"]._render_template(
            self.body or "", self.res_model, records.ids, engine="inline_template"
        )
        msgs = self.env["evo.whatsapp.message"].sudo()._evo_enqueue(
            records,
            bodies=bodies,
            template=self.template_id,
            attachments=self.attachment_ids,
            report=self.report_id,
            recipient_type=self.recipient_type,
            user_field=self.user_field_id.name,
            fixed_numbers=self.fixed_numbers,
        )
        no_phone = len(msgs.filtered(lambda m: not m.phone))
        message = _("%s WhatsApp message(s) queued; sending starts within a minute.", len(msgs))
        if no_phone:
            message += " " + _("%s without a valid phone will be marked Failed.", no_phone)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("WhatsApp"),
                "message": message,
                "type": "warning" if no_phone else "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
