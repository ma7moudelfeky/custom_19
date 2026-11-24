"""Upgrade from the old invoice-only whatsapp_evolution_invoice (19.0.1.x).

The old module's views reference fields that no longer exist (evo_auto_send,
wa_state, ...). Odoo only removes obsolete records at the END of an upgrade,
but validates the new views (combined with the stale ones) while loading, so
the upgrade crashes. Remove the stale views/cron before anything is loaded.
"""
import logging

_logger = logging.getLogger(__name__)

OLD_VIEWS = (
    "res_config_settings_view_form_whatsapp_evolution",
    "view_move_form_whatsapp_evolution",
    "view_invoice_tree_whatsapp_evolution",
    "view_account_invoice_filter_whatsapp_evolution",
)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
         WHERE module = 'whatsapp_evolution_invoice' AND model = 'ir.ui.view' AND name IN %s
        """,
        [OLD_VIEWS],
    )
    view_ids = [r[0] for r in cr.fetchall()]
    if view_ids:
        # child views first (none expected), then the stale views themselves
        cr.execute("DELETE FROM ir_ui_view WHERE inherit_id IN %s", [tuple(view_ids)])
        cr.execute("DELETE FROM ir_ui_view WHERE id IN %s", [tuple(view_ids)])
        cr.execute(
            "DELETE FROM ir_model_data WHERE module = 'whatsapp_evolution_invoice'"
            " AND model = 'ir.ui.view' AND name IN %s",
            [OLD_VIEWS],
        )
    # The old cron calls a method that no longer exists; Odoo deletes it at the end.
    cr.execute(
        """
        UPDATE ir_cron SET active = false WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'whatsapp_evolution_invoice' AND model = 'ir.cron'
               AND name = 'ir_cron_send_whatsapp_invoices')
        """
    )
    _logger.info("whatsapp_evolution_invoice: removed %s stale view(s) from 19.0.1.x", len(view_ids))
