import base64
import logging
import random
import re
import time

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def normalize_egypt_phone(raw):
    """Return digits-only international number, adding Egypt's 20 code to local 01x numbers."""
    digits = re.sub(r'\D', '', raw or '')
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('01') and len(digits) == 11:
        digits = '20' + digits[1:]
    elif digits.startswith('1') and len(digits) == 10:
        digits = '20' + digits
    return digits


class AccountMove(models.Model):
    _inherit = 'account.move'

    wa_state = fields.Selection(
        [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')],
        string='WhatsApp Status', copy=False, readonly=True,
    )
    wa_sent_date = fields.Datetime(string='WhatsApp Sent On', copy=False, readonly=True)
    wa_sent_to = fields.Char(string='WhatsApp Sent To', copy=False, readonly=True)
    wa_error = fields.Char(string='WhatsApp Error', copy=False, readonly=True)

    def _wa_param(self, key, default=None):
        return self.env['ir.config_parameter'].sudo().get_param('whatsapp_evolution.' + key, default)

    def _wa_phone(self):
        self.ensure_one()
        partner = self.partner_id
        raw = partner.phone
        if 'mobile' in partner._fields and partner.mobile:
            raw = partner.mobile
        return normalize_egypt_phone(raw)

    def action_post(self):
        res = super().action_post()
        if self._wa_param('auto_send'):
            to_send = self.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund'))
            if to_send:
                to_send.wa_state = 'pending'
                self.env.ref('whatsapp_evolution_invoice.ir_cron_send_whatsapp_invoices')._trigger()
        return res

    def action_wa_send(self):
        self.filtered(lambda m: m.state == 'posted').wa_state = 'pending'
        self.env.ref('whatsapp_evolution_invoice.ir_cron_send_whatsapp_invoices')._trigger()

    def _wa_send_now(self):
        self.ensure_one()
        url = (self._wa_param('api_url') or '').rstrip('/')
        key = self._wa_param('api_key')
        instance = self._wa_param('instance')
        if not (url and key and instance):
            raise UserError(_('Evolution API is not configured in Settings.'))
        phone = self._wa_phone()
        if len(phone) < 10:
            raise UserError(_('Customer has no valid phone number.'))

        pdf, _type = self.env['ir.actions.report']._render_qweb_pdf('account.account_invoices', self.ids)
        file_name = '%s.pdf' % (self.name or 'invoice').replace('/', '_')
        caption = _('Dear %(partner)s, please find attached invoice %(name)s for %(amount)s.',
                    partner=self.partner_id.name, name=self.name,
                    amount=self.currency_id.format(self.amount_total))
        resp = requests.post(
            '%s/message/sendMedia/%s' % (url, instance),
            headers={'apikey': key, 'Content-Type': 'application/json'},
            json={
                'number': phone,
                'mediatype': 'document',
                'mimetype': 'application/pdf',
                'caption': caption,
                'media': base64.b64encode(pdf).decode(),
                'fileName': file_name,
            },
            timeout=60,
        )
        if resp.status_code >= 300:
            raise UserError(_('Evolution API error %(code)s: %(body)s',
                              code=resp.status_code, body=resp.text[:500]))
        return phone

    @api.model
    def _cron_send_whatsapp_invoices(self):
        batch_size = int(self._wa_param('batch_size', 5) or 5)
        delay_min = int(self._wa_param('delay_min', 8) or 0)
        delay_max = max(int(self._wa_param('delay_max', 20) or 0), delay_min)
        moves = self.search([('wa_state', '=', 'pending')], limit=batch_size, order='id')
        for i, move in enumerate(moves):
            if i:
                time.sleep(random.uniform(delay_min, delay_max))
            try:
                phone = move._wa_send_now()
                move.write({
                    'wa_state': 'sent',
                    'wa_sent_date': fields.Datetime.now(),
                    'wa_sent_to': phone,
                    'wa_error': False,
                })
                move.message_post(body=_('Invoice sent on WhatsApp to %s.', phone))
            except Exception as e:
                _logger.warning('WhatsApp send failed for %s: %s', move.name, e)
                move.write({'wa_state': 'failed', 'wa_error': str(e)[:250]})
                move.message_post(body=_('WhatsApp sending failed: %s', e))
            self.env.cr.commit()
        if self.search_count([('wa_state', '=', 'pending')], limit=1):
            self.env.ref('whatsapp_evolution_invoice.ir_cron_send_whatsapp_invoices')._trigger()
