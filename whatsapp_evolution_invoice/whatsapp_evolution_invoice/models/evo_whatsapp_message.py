import base64
import logging
import random
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

from .evo_client import EvolutionClient, EvolutionError, normalize_phone
from .evo_whatsapp_template import RECIPIENT_TYPES

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# Seconds one cron run may spend (sending + random sleeps), well under the
# default 120s worker real-time limit so the cron is never killed mid-batch.
CRON_TIME_BUDGET = 75


class EvoWhatsappMessage(models.Model):
    _name = "evo.whatsapp.message"
    _description = "WhatsApp Message (Evolution API)"
    _order = "id desc"
    _rec_name = "record_name"

    res_model = fields.Char(string="Model", index=True)
    res_id = fields.Many2oneReference(string="Record ID", model_field="res_model", index=True)
    record_name = fields.Char(string="Record")
    template_id = fields.Many2one("evo.whatsapp.template", ondelete="set null", index=True)
    recipient_name = fields.Char(string="Recipient")
    raw_phone = fields.Char(string="Phone (as entered)")
    phone = fields.Char(string="WhatsApp Number")
    body = fields.Text()
    attachment_ids = fields.Many2many(
        "ir.attachment", "evo_whatsapp_message_attachment_rel", "message_id", "attachment_id",
        string="Attachments",
    )
    report_id = fields.Many2one("ir.actions.report", string="PDF Report", ondelete="set null")
    dedupe_key = fields.Char(index=True, copy=False)
    state = fields.Selection(
        [("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"), ("cancel", "Cancelled")],
        default="pending", required=True, index=True,
    )
    attempts = fields.Integer(default=0)
    error = fields.Text()
    sent_date = fields.Datetime()
    wa_message_id = fields.Char(string="WhatsApp Msg ID")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)

    # ------------------------------------------------------------------ params
    @api.model
    def _get_param(self, key, default=None):
        return self.env["ir.config_parameter"].sudo().get_param(f"evo_whatsapp.{key}", default)

    @api.model
    def _get_client(self):
        return EvolutionClient(
            self._get_param("api_url", "http://evolution_api:8080"),
            self._get_param("api_key"),
            self._get_param("instance", "odoo"),
        )

    @api.model
    def _check_number_enabled(self):
        return self._get_param("check_number", "True") not in ("False", "0", "")

    # -------------------------------------------------------------- recipients
    @api.model
    def _evo_phone_of(self, rec):
        for fname in ("mobile", "mobile_phone", "phone"):
            if fname in rec._fields and rec[fname]:
                return rec[fname]
        if "partner_id" in rec._fields and rec.partner_id and rec.partner_id != rec:
            return self._evo_phone_of(rec.partner_id)
        return False

    @api.model
    def _evo_recipients(self, record, recipient_type="record", user_field=None, fixed_numbers=None):
        """List of (name, raw_phone) for one record."""
        if recipient_type == "users":
            users = record[user_field] if user_field and user_field in record._fields else False
            return [(u.name, self._evo_phone_of(u)) for u in (users or [])]
        if recipient_type == "fixed":
            return [(n.strip(), n.strip()) for n in (fixed_numbers or "").split(",") if n.strip()]
        name = record.display_name
        if "partner_id" in record._fields and record.partner_id:
            name = record.partner_id.display_name
        if "contact_name" in record._fields and record.contact_name:
            name = record.contact_name
        return [(name, self._evo_phone_of(record))]

    @api.model
    def _evo_enqueue(self, records, bodies, template=None, attachments=None, report=None,
                     recipient_type="record", user_field=None, fixed_numbers=None, dedupe=None):
        """Create pending messages. ``bodies``: {res_id: text}. Duplicate keys are skipped."""
        cc = self._get_param("country_code", "20")
        vals_list, seen = [], set()
        for record in records:
            base_key = dedupe(record) if dedupe else None
            for name, raw in self._evo_recipients(record, recipient_type, user_field, fixed_numbers):
                phone = normalize_phone(raw, cc) or False
                key = f"{base_key}:{phone or raw}" if base_key else False
                if key:
                    if key in seen or self.search_count(
                        [("dedupe_key", "=", key), ("state", "in", ("pending", "sent"))]
                    ):
                        continue
                    seen.add(key)
                vals_list.append({
                    "res_model": record._name,
                    "res_id": record.id,
                    "record_name": record.display_name,
                    "template_id": template.id if template else False,
                    "recipient_name": name,
                    "raw_phone": raw,
                    "phone": phone,
                    "body": bodies.get(record.id, ""),
                    "attachment_ids": [(6, 0, attachments.ids if attachments else [])],
                    "report_id": report.id if report else False,
                    "dedupe_key": key,
                })
        return self.create(vals_list) if vals_list else self.browse()

    # ------------------------------------------------------------------ helpers
    def _record(self):
        self.ensure_one()
        if self.res_model in self.env and self.res_id:
            return self.env[self.res_model].sudo().browse(self.res_id).exists()
        return None

    def _log_on_record(self, body):
        rec = self._record()
        if rec and hasattr(rec, "message_post"):
            rec.message_post(body=body)

    def _media_payloads(self):
        """[(b64, filename, mimetype)] — report rendered fresh at send time."""
        self.ensure_one()
        items = []
        rec = self._record()
        if self.report_id and rec:
            pdf, _fmt = self.env["ir.actions.report"].sudo()._render_qweb_pdf(
                self.report_id, rec.ids
            )
            fname = (rec.display_name or "document").replace("/", "_")
            items.append((base64.b64encode(pdf).decode(), f"{fname}.pdf", "application/pdf"))
        for att in self.attachment_ids.sudo():
            if att.datas:
                items.append((att.datas.decode(), att.name, att.mimetype))
        return items

    # ------------------------------------------------------------------ sending
    def _send_one(self, client, check_number=True):
        """Send this message once. Never raises; updates state."""
        self.ensure_one()
        who = f"{self.recipient_name or ''} ({self.raw_phone or '-'})"
        if not self.phone:
            self.write({"state": "failed", "error": _("Invalid or missing phone: %s", who)})
            self._log_on_record(_("WhatsApp not sent: invalid/missing phone for %s.", who))
            return False
        try:
            if check_number and client.has_whatsapp(self.phone) is False:
                self.write({"state": "failed",
                            "error": _("Number %s has no WhatsApp account.", self.phone)})
                self._log_on_record(_("WhatsApp not sent: %s has no WhatsApp.", self.phone))
                return False
            media = self._media_payloads()
            typing = random.randint(1200, 3500)
            if not media:
                msg_id = client.send_text(self.phone, self.body or "", typing_delay_ms=typing)
            else:
                msg_id = ""
                for idx, (b64, fname, mime) in enumerate(media):
                    mid = client.send_media(
                        self.phone, b64, fname, mime,
                        caption=self.body if idx == 0 else "",
                        typing_delay_ms=typing if idx == 0 else 800,
                    )
                    msg_id = msg_id or mid
        except EvolutionError as exc:
            attempts = self.attempts + 1
            self.write({
                "attempts": attempts,
                "error": str(exc),
                "state": "failed" if attempts >= MAX_ATTEMPTS else "pending",
            })
            _logger.warning("WhatsApp send failed (%s): %s", self.record_name, exc)
            return False
        except Exception as exc:  # report rendering, bad attachment...
            _logger.exception("WhatsApp send crashed (%s)", self.record_name)
            self.write({"state": "failed", "attempts": self.attempts + 1, "error": str(exc)})
            return False
        self.write({"state": "sent", "sent_date": fields.Datetime.now(),
                    "wa_message_id": msg_id, "error": False, "attempts": self.attempts + 1})
        self._log_on_record(_("WhatsApp sent to %(name)s (+%(phone)s).",
                              name=self.recipient_name or "", phone=self.phone))
        return True

    @api.model
    def _cron_process_queue(self):
        """Send pending messages with a random human-like gap between each one."""
        pending = self.search([("state", "=", "pending")], order="id asc", limit=50)
        if not pending:
            return
        try:
            client = self._get_client()
        except EvolutionError as exc:
            _logger.warning("WhatsApp queue skipped: %s", exc)
            return
        dmin = max(1, int(self._get_param("delay_min", 8) or 8))
        dmax = max(dmin, int(self._get_param("delay_max", 20) or 20))
        check = self._check_number_enabled()
        testing = config["test_enable"]
        start = time.monotonic()
        for idx, msg in enumerate(pending):
            if idx:
                gap = random.uniform(dmin, dmax)
                if time.monotonic() - start + gap > CRON_TIME_BUDGET:
                    break  # the rest waits for the next cron run
                if not testing:
                    time.sleep(gap)
            msg._send_one(client, check_number=check)
            if not testing:
                # Persist each result so a timeout never re-sends a delivered message
                self.env.cr.commit()  # pylint: disable=invalid-commit

    # ------------------------------------------------------------------ buttons
    def action_retry(self):
        cc = self._get_param("country_code", "20")
        for msg in self.filtered(lambda m: m.state in ("failed", "cancel")):
            msg.write({"state": "pending", "attempts": 0, "error": False,
                       "phone": normalize_phone(msg.raw_phone, cc) or False})

    def action_cancel(self):
        self.filtered(lambda m: m.state == "pending").write({"state": "cancel"})

    def action_send_now(self):
        try:
            client = self._get_client()
        except EvolutionError as exc:
            raise UserError(str(exc)) from exc
        check = self._check_number_enabled()
        for msg in self.filtered(lambda m: m.state == "pending"):
            msg._send_one(client, check_number=check)

    def action_open_record(self):
        self.ensure_one()
        return {"type": "ir.actions.act_window", "res_model": self.res_model,
                "res_id": self.res_id, "view_mode": "form", "target": "current"}


__all__ = ["EvoWhatsappMessage", "RECIPIENT_TYPES"]
