from odoo import models, fields, api


class BroadcastChannel(models.Model):
    _name = "broadcast.channel"
    _description = "Broadcast Channel"

    name = fields.Char(string="Channel Name", required=True)
    color = fields.Integer(string="Color")
