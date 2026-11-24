from odoo import api, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @api.model_create_multi
    def create(self, vals_list):
        leads = super().create(vals_list)
        leads._evo_stage_trigger()
        return leads

    def write(self, vals):
        res = super().write(vals)
        if "stage_id" in vals:
            self._evo_stage_trigger()
        return res

    def _evo_stage_trigger(self):
        leads = self.filtered("stage_id")
        if not leads:
            return
        templates = self.env["evo.whatsapp.template"].sudo().search([
            ("trigger", "=", "crm_stage"),
            ("model", "=", "crm.lead"),
            ("stage_ids", "in", leads.stage_id.ids),
        ])
        for tmpl in templates:
            targets = leads.filtered(lambda lead, t=tmpl: lead.stage_id in t.stage_ids)
            # Once per lead per stage: moving back and forth does not spam the customer.
            tmpl._enqueue_for(
                targets, dedupe=lambda lead, t=tmpl: f"stg{t.id}:{lead.id}:{lead.stage_id.id}"
            )
