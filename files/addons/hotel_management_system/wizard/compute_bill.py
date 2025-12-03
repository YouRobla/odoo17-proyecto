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
from odoo import fields, models, _, api


class ComputeBill(models.TransientModel):
    _name = "booking.bill"
    _description = "To compute bill of room service"

    def onchange_room_service(self):
        total_booking_ids = self._generate_room_bill_info()
        if total_booking_ids:
            return [(6, 0, total_booking_ids)]
        else:
            return [(6, 0, [])]

    room_service_ids = fields.One2many("service.bill", "service_id")
    print_bill = fields.Selection(
        [("combine", "Combined Bill"), ("separate", "Isolate Bill")], default="combine"
    )
    is_hide_print_bill = fields.Boolean(compute="compute_hide_printbill")
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        readonly=True,
    )
    booking_id = fields.Many2one("hotel.booking")
    order_ids = fields.Many2many(
        "sale.order",
        "sale_order_bill_rel",
        "sale_order_id",
        "bill_id",
        string="Sale order",
        default=onchange_room_service,
    )

    @api.depends("order_ids")
    def compute_hide_printbill(self):
        if hasattr(self, "pos_order_ids") and self.pos_order_ids:
            self.is_hide_print_bill = False
        else:
            self.is_hide_print_bill = True

    def _get_booking_id(self, booking_id):
        order_ids = self.env["sale.order"].search(
            [("booking_id", "=", booking_id.id), ("state", "=", "sale")]
        )
        if booking_id.order_id.id not in order_ids.ids:
            order_ids += booking_id.order_id
        return order_ids

    def _generate_room_bill_info(self):
        booking_id = self.env["hotel.booking"].browse(self._context.get("active_ids"))
        return self._get_booking_id(booking_id).ids

    def print_detailed_report(self):
        booking_id = self.env["hotel.booking"].browse(self._context.get("active_ids"))
        self.booking_id = booking_id.id
        self.partner_id = booking_id.partner_id.id
        self._generate_room_bill_info()
        self.order_ids = self._get_booking_id(booking_id)
        return self.env.ref(
            "hotel_management_system.action_report_booking_detailed_bill"
        ).report_action(self)

    def print_report(self):
        booking_id = self.env["hotel.booking"].browse(self._context.get("active_ids"))
        self.booking_id = booking_id.id
        self.partner_id = booking_id.partner_id.id
        self._generate_room_bill_info()

        if self.print_bill != "combine":    
            self.order_ids = self._get_booking_id(booking_id)
            return self.env.ref(
                "hotel_management_system.action_report_booking_separate"
            ).report_action(self)
        else:
            self.order_ids = self._get_booking_id(booking_id)
            return self.env.ref(
                "hotel_management_system.action_report_booking_combine"
            ).report_action(self)


class RoomServiceBill(models.TransientModel):
    _name = "service.bill"
    _description = "Room Service Bill"

    name = fields.Char("Name")
    reference = fields.Char("Reference No")
    service_id = fields.Many2one("booking.bill")
    date_order = fields.Date("Order Date")
    amount_total = fields.Float("Amount Total")
