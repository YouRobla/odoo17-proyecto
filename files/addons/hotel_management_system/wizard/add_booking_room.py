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
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ADDROOM(models.TransientModel):
    _name = "booking.room"
    _description = "Show rooms if available"

    @api.onchange("available_room_ids")
    def _onchange_get_available_rooms(self):
        if self._context.get("active_model") == "sale.order":
            active_booking_id = self.env["sale.order"].browse(
                self._context.get("active_ids")
            )
            check_in = active_booking_id.hotel_check_in
            check_out = active_booking_id.hotel_check_out
        else:
            active_booking_id = self.env["hotel.booking"].browse(
                self._context.get("active_ids")
            )
            check_in = active_booking_id.check_in
            check_out = active_booking_id.check_out

        if not active_booking_id.hotel_id:
            raise UserError(_("Please select Hotel first..."))

        if (check_in or check_out) is False:
            raise UserError(_("Please select Check in/out date first..."))

        booking = self.env["hotel.booking"].search([])
        product_ids = self.env["product.product"].search(
            [('hotel_id', '!=', active_booking_id.hotel_id.id)])

        for line in booking:
            if line.filter_booking_based_on_date(check_in, check_out):
                product_ids += line.mapped("booking_line_ids.product_id")
        self.write({"booked_booking_ids": product_ids})

    available_room_ids = fields.Many2many(
        "product.product",
        "product_add_room_rel",
        "product_id",
        "booking_available_room_line_id",
        string="Available Room",
        readonly=False,
        domain="[('product_tmpl_id.is_room_type','=',True)]",
    )
    guestinfo_ids = fields.Many2many("guest.info", string="Guest Info")
    booked_booking_ids = fields.Many2many("product.product")

    def add_room_in_booking(self):
        if self._context.get("active_model") == "sale.order":
            active_booking_id = self.env["sale.order"].browse(
                self._context.get("active_ids")
            )
            if self.available_room_ids:
                product_uom_qty = (
                    active_booking_id.hotel_check_out.date()
                    - active_booking_id.hotel_check_in.date()
                ).days or 1
                active_booking_id.order_line = [
                    (
                        0,
                        0,
                        {
                            "product_id": line.id,
                            "product_uom_qty": product_uom_qty,
                            "guest_info_ids": [
                                (4, guest_id) for guest_id in self.guestinfo_ids.ids
                            ],
                        },
                    )
                    for line in self.available_room_ids
                ]
            else:
                return UserError(_("Select rooms for adding in booking..."))
        else:
            active_booking_id = self.env["hotel.booking"].browse(
                self._context.get("active_ids")
            )
            if self.available_room_ids:
                active_booking_id.booking_line_ids = [
                    (
                        0,
                        0,
                        {
                            "product_id": line.id,
                            "tax_ids": line.taxes_id,
                        },
                    )
                    for line in self.available_room_ids
                ]
            else:
                return UserError(_("Select rooms for adding in booking..."))
