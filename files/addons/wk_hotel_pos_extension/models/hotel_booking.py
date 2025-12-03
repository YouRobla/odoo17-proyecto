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
from odoo import fields, models,api

class HotelBooking(models.Model):
    """Module to manage Hotel Booking

    Parameters
    ----------
    models : importing Model
    """
    _inherit = "hotel.booking"
    pos_order_ids = fields.One2many('pos.order','booking_id', string="Pos Order")
    pos_invoice_count = fields.Integer('Invoice count', copy = False, compute="_compute_pos_invoice_count")

    def _compute_pos_invoice_count(self):
         for rec in self:
            rec.pos_invoice_count = len(rec.pos_order_ids.mapped('account_move').ids)

    @api.model
    def fetch_booked_room_data_for_pos(self):
            booking=self.env['hotel.booking']
            booking_ids = booking.search([('booking_line_ids','!=',False),('status_bar','=', 'allot')])
            return [
                {
                    'booking_id':rec.id,
                    'booking_customer':rec.partner_id.name,
                    'customer_id':rec.partner_id.id,
                    'booking_name':rec.sequence_id,
                    'lines':rec.booking_line_ids.read(['id', 'product_id', 'booking_id'])
                } for rec in booking_ids
            ]

    def pos_invoice_and_order_view(self):
        """POS invoice & order View

        Returns
        -------
        Open View in tree mode
        """
        if self.env.context.get('action_name',False) == 'pos_invoice':
            action_name = "Invoice"
            model_name = "account.move"
            record_ids = self.pos_order_ids.mapped('account_move').ids
        else:
            action_name = "Pos Order"
            model_name = "pos.order"
            record_ids = self.pos_order_ids.ids
        return {
            "name": action_name,
            "type": "ir.actions.act_window",
            "res_model": model_name,
            "view_mode": 'tree,form',
            'domain': [('id', 'in', record_ids)],
            "target": "current"
        }
