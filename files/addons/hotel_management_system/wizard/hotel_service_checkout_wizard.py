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
from odoo import models, fields


class HotelServiceCheckoutWizard(models.TransientModel):
    _name = "hotel.service.checkout.wizard"
    _description = "Checkout Pending Services"

    service_ids = fields.Many2many(
        "hotel.booking.service.line", string="Pending Services")
    checkout = fields.Boolean()
    booking_id = fields.Many2one("hotel.booking", string="Booking")

    def mark_all_done(self):
        for line in self.service_ids:
            if line.state in ["draft", "confirm"]:
                line.state = "done"
        self.checkout = True
        return {
            "type": "ir.actions.act_window",
            "res_model": "hotel.service.checkout.wizard",
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_checkout(self):
        if self.booking_id:
            self.booking_id.action_checkout()
        return {"type": "ir.actions.act_window_close"}
