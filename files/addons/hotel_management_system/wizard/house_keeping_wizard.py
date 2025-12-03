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
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class HouseKeepingWizard(models.TransientModel):
    _name = "hotel.housekeeping.wizard"
    _description = "House Keeping Wizard"

    booking_id = fields.Many2one(
        'hotel.booking', string="Booking", required=True)
    assign_to = fields.Many2one(
        'res.users', string="Assign To", required=True)
    state = fields.Selection([('draft', 'Draft'), ('in_progress',
                              'In Progress'), ('completed', 'Completed')], default='draft')
    room_id = fields.Many2one("product.product", string="Rooms", required=True)

    def create_housekeeping(self):
        self.env['hotel.housekeeping'].create({
            'booking_id': self.booking_id.id,
            'state': 'draft',
            'assign_to': self.assign_to.id,
            'room_id': self.room_id
        })
        self.booking_id.status_bar = 'checkout'
