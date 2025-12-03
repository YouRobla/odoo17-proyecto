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
from odoo import fields, models, _


class ExchangeRoom(models.TransientModel):
    _name = "booking.cancel"
    _description = "Booking cancellation"

    cancellation_reason = fields.Text("Cancellation Reason", required=True)

    def confirm_booking_cancel(self):
        """Confirm Booking Cancellation wizard"""
        active_booking_id = self.env["hotel.booking"].browse(
            self._context.get("active_ids")
        )
        active_booking_id.write(
            {"cancellation_reason": self.cancellation_reason, "status_bar": "cancel"}
        )
        template_id = self.env.ref(
            "hotel_management_system.hotel_booking_cancel_id")
        template_id.send_mail(active_booking_id.id, force_send=True)
        if active_booking_id.order_id:
            self.env['sale.order.cancel'].create(
                {'order_id': active_booking_id.order_id.id}).action_cancel()
            active_booking_id.order_id.message_post(
                body=("Cancellation Reason => " + self.cancellation_reason))
