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


class HotelAddRoomsWizard(models.TransientModel):
    _name = 'hotel.add.rooms.wizard'
    _description = 'Add Rooms to Hotel'

    room_ids = fields.Many2many(
        'product.template',
        string='Rooms',
        domain=[('is_room_type', '=', True), ('hotel_id', '=', False)],
        help="Select rooms to add to the hotel.",
    )
    hotel_id = fields.Many2one('hotel.hotels', string='Hotel', required=True)

    def action_add_rooms(self):
        """Add the selected rooms to the hotel."""
        for room in self.room_ids:
            room.hotel_id = self.hotel_id
