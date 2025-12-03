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
from odoo import api, fields, models, _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)


class ComputeBill(models.TransientModel):
    _inherit = "booking.bill"

    def onchange_pos_invoice(self):
        booking_id = self.env['hotel.booking'].browse(self._context.get("active_ids"))
        if booking_id:
            return [(6, 0, booking_id.pos_order_ids.ids)]

    # -------------------------------------------------------------------------//
    # MODEL FIELDS
    # -------------------------------------------------------------------------//
    pos_order_ids = fields.Many2many('pos.order', 'pos_order_bill_rel', 'pos_order_id', 'pos_bill_id',
                                        string='Pos order',default=onchange_pos_invoice)
