from odoo import fields, models


class EvoWhatsappTemplate(models.Model):
    _inherit = "evo.whatsapp.template"

    trigger = fields.Selection(
        selection_add=[("crm_stage", "When the lead reaches a stage")],
        ondelete={"crm_stage": "set default"},
    )
    stage_ids = fields.Many2many(
        "crm.stage", "evo_whatsapp_template_crm_stage_rel", "template_id", "stage_id",
        string="Stages",
    )
