from odoo import fields, models


class EvoWhatsappTemplate(models.Model):
    _inherit = "evo.whatsapp.template"

    trigger = fields.Selection(
        selection_add=[("invoice_post", "On invoice confirm")],
        ondelete={"invoice_post": "set default"},
    )
