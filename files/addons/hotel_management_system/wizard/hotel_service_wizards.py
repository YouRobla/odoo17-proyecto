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
import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class HotelServiceWizard(models.TransientModel):
    _name = "hotel.service.wizard"
    _description = "Select Hotel Service Wizard"

    booking_line_id = fields.Many2one(
        "hotel.booking.line",
        string="Room",
        required=True,
        domain="[('booking_id', '=', booking_id)]",
    )
    booking_id = fields.Many2one(related="booking_line_id.booking_id")
    service_id = fields.Many2one(
        "hotel.service", string="Service", required=True)
    assign_to = fields.Many2one("res.partner", string="Assign To")
    service_type = fields.Selection(related="service_id.service_type")
    product_id = fields.Many2one(related="service_id.product_id")
    amount = fields.Float("Amount")
    note = fields.Text("Notes")

    @api.onchange("service_id")
    def _set_amount(self):
        if self.service_id and self.service_type:
            self.amount = self.service_id.amount if self.service_type == "paid" else 0
        else:
            self.amount = 0

    def action_add_service(self):
        self.env["hotel.booking.service.line"].create(
            {
                "booking_line_id": self.booking_line_id.id,
                "service_id": self.service_id.id,
                "amount": self.amount if self.service_type == "paid" else 0,
                "assign_to": self.assign_to.id if self.assign_to else False,
                "note": self.note,
                "state": "confirm",
            }
        )
