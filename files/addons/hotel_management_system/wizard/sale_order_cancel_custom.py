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
from odoo import models, api, fields


class SaleOrderCancelCustom(models.TransientModel):
    _inherit = 'sale.order.cancel'

    cancellation_reason = fields.Text("Cancellation Reason")
    show_reason_field = fields.Boolean(
        string="Show Reason", compute="_compute_show_reason")

    @api.depends('order_id')
    def _compute_show_reason(self):
        for wizard in self:
            wizard.show_reason_field = bool(wizard.order_id.booking_id)

    def action_cancel(self):
        '''
        Overriding for cancellation_reason and for sending Email
        '''
        booking_id = self.order_id.booking_id
        if booking_id and self.cancellation_reason:
            booking_id.write(
                {"cancellation_reason": self.cancellation_reason,
                    "status_bar": "cancel"}
            )
            template_id = self.env.ref(
                "hotel_management_system.hotel_booking_cancel_id")
            template_id.send_mail(booking_id.id, force_send=True)
            self.env['sale.order.cancel'].create(
                {'order_id': self.order_id.id}).action_cancel()
            self.order_id.message_post(
                body=("Cancellation Reason => " + self.cancellation_reason))
        result = super().action_cancel()
        return result
