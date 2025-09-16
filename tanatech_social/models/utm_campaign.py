from odoo import models, fields, api


class UtmCampaign(models.Model):
    _inherit = "utm.campaign"

    company_currency_id = fields.Many2one(
        "res.currency", string="Currency", compute="_compute_currency"
    )

    def _compute_currency(self):
        for rec in self:
            rec.company_currency_id = self.env.company.currency_id.id

    date_from = fields.Datetime(string="Start Date")
    date_to = fields.Datetime(string="End Date")
    broadcast_line_ids = fields.One2many(
        "utm.campaign.broadcast", "campaign_id", string="Broadcast Channels"
    )

    # budget_total = fields.Float(
    #     string="Total Budget", compute="_compute_budget_total", store=True
    # )
    budjet_total = fields.Monetary(
        string="Total Budget",
        currency_field="company_currency_id",
        compute="_compute_budget_total",
        store=True,
    )

    @api.depends("broadcast_line_ids.budget")
    def _compute_budget_total(self):
        for rec in self:
            rec.budjet_total = sum(rec.broadcast_line_ids.mapped("budget") or [0.0])


class UtmCampaignBroadcast(models.Model):
    _name = "utm.campaign.broadcast"
    _description = "Campaign Broadcast Line"

    campaign_id = fields.Many2one("utm.campaign", string="Campaign", ondelete="cascade")
    broadcast_channel_id = fields.Many2one(
        "broadcast.channel", string="Broadcast Channel", required=True
    )
    budget = fields.Float(string="Budget")
