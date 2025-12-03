# -*- coding: utf-8 -*-
##########################################################################
# Author : Webkul Software Pvt. Ltd. (<https://webkul.com/>;)
# Copyright(c): 2017-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>;
##########################################################################

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HouseKeeping(models.Model):
    _name = "hotel.housekeeping"
    _description = "House Keeping"
    _rec_name = "sequence_id"

    sequence_id = fields.Char(
        string="Sequence",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("New"),
    )
    assign_to = fields.Many2one("res.users", string="Assign To")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
        ],
        default="draft",
        string="state",
    )
    booking_line_id = fields.Many2one(
        "hotel.booking.line", string="Booking Line")
    booking_id = fields.Many2one(related="booking_line_id.booking_id")
    image_1920 = fields.Image(string="Image", related="assign_to.image_1920")
    room_id = fields.Many2one("product.product", string="Rooms", required=True)
    responsible = fields.Many2one("res.users", string="Responsible ")
    team_id = fields.Many2one("crm.team", string="Housekeeping Team")

    def action_in_progress(self):
        for rec in self:
            if not rec.assign_to:
                raise UserError(_("Please set the Assign To first."))
            rec.state = "in_progress"

    def action_completed(self):
        for rec in self:
            if rec.state != "in_progress":
                raise UserError(
                    _("Housekeeping must be in progress to mark as completed."))
            rec.state = "completed"

    def action_draft(self):
        for rec in self:
            rec.state = "draft"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "company_id" in vals:
                self = self.with_company(vals["company_id"])
            if vals.get("sequence_id", _("New")) == _("New"):
                seq_date = (
                    fields.Datetime.context_timestamp(
                        self, fields.Datetime.to_datetime(vals["check_in"])
                    )
                    if "check_in" in vals
                    else None
                )
                vals["sequence_id"] = self.env["ir.sequence"].next_by_code(
                    "hotel.housekeeping", sequence_date=seq_date
                ) or _("New")
        return super().create(vals_list)
