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

class PosOrder(models.Model):
    _inherit = 'pos.order'

    booking_id = fields.Many2one('hotel.booking', string="Hotel Booking", related='booking_line_id.booking_id')
    booking_line_id = fields.Many2one('hotel.booking.line', string="Hotel Booking Line")
    # state = fields.Selection(
    #     selection_add=[('unpaid_invoice', 'Unpaid Invoice')])

    @api.model
    def _order_fields(self, ui_order):
        order_fields = super(PosOrder, self)._order_fields(ui_order)
        order_fields['booking_id'] = ui_order.get('booking_id')
        order_fields['booking_line_id'] = ui_order.get('booking_line_id')
        return order_fields

    @api.model
    def _process_order(self, order, draft, existing_order):
        res = super(PosOrder, self)._process_order(order, draft, existing_order)
        pos_order = self.browse(res)
        if pos_order.booking_id and pos_order.to_invoice:
            pos_order._generate_pos_order_invoice()
        return res

    def write(self, vals):
        for order in self:
            if order.name == '/' and order.booking_id:
                vals['name'] = self._compute_order_name()
        return super(PosOrder, self).write(vals)

    def action_pos_order_paid(self):
        self.ensure_one()
        if not self.booking_id:
            return super(PosOrder, self).action_pos_order_paid()
        
    def action_view_booking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Booking",
            "res_model": "hotel.booking",
            "view_mode": "form",
            "res_id": self.booking_id.id,
            "views": [(self.env.ref("hotel_management_system.hotel_booking_view_form").id, "form")],
            "target": "current",
        }
