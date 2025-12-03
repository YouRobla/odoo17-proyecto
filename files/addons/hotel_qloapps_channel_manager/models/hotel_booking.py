# -*- coding: utf-8 -*-
##########################################################################
#
#    Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#
##########################################################################

import logging

from odoo import models, fields, _, api
from odoo.exceptions import UserError
from datetime import datetime

_logger = logging.getLogger(__name__)


class HotelBooking(models.Model):
    _inherit = "hotel.booking"

    # Creating a new field for determining if the booking is modified or not.
    need_to_sync = fields.Boolean("Need to sync?")

    def write(self, vals):
        """
        This method is used for setting the need_to_sync field to True if the booking is modified for specific fields.
        """
        for record in self:
            need_sync = False
            if record.booking_reference == "other":
                if "status_bar" in vals and vals["status_bar"] == "cancel":
                    need_sync = True

                if "check_in" in vals and vals["check_in"] != record.check_in:
                    need_sync = True
                if "check_out" in vals and vals["check_out"] != record.check_out:
                    need_sync = True

                if "booking_line_ids" in vals:
                    old_count = len(record.booking_line_ids)
                    new_count = (
                        len(vals["booking_line_ids"])
                        if isinstance(vals["booking_line_ids"], list)
                        else old_count
                    )
                    if new_count != old_count:
                        need_sync = True
                    else:
                        for line in record.booking_line_ids:
                            for changes in vals["booking_line_ids"]:
                                if (
                                    isinstance(changes, (list, tuple))
                                    and changes[0] == 1
                                ):
                                    line_id, updated_values = changes[1], changes[2]
                                    if (
                                        line.id == line_id
                                        and "room_id" in updated_values
                                        and updated_values["room_id"] != line.room_id.id
                                    ):
                                        need_sync = True
                                        break
                            if need_sync:
                                break

            if need_sync:
                vals["need_to_sync"] = True

        return super(HotelBooking, self).write(vals)

    def get_filtered_bookings(self, **kwargs):
        """
        Fetch filtered booking details based on API request parameters.
        Returns: -> An array of booking detail's object/dict
        """
        domain = []

        if "filter[id_property]" in kwargs:
            domain.append(("hotel_id", "=", int(
                kwargs["filter[id_property]"])))

        date_filters = {
            "filter[date_updated][gte]": ("write_date", ">="),
            "filter[date_updated][gt]": ("write_date", ">"),
            "filter[date_updated][lt]": ("write_date", "<"),
            "filter[date_updated][lte]": ("write_date", "<="),
            "filter[check_in][gte]": ("check_in", ">="),
            "filter[check_in][gt]": ("check_in", ">"),
            "filter[check_in][lt]": ("check_in", "<"),
            "filter[check_in][lte]": ("check_in", "<="),
            "filter[check_out][gte]": ("check_out", ">="),
            "filter[check_out][gt]": ("check_out", ">"),
            "filter[check_out][lt]": ("check_out", "<"),
            "filter[check_out][lte]": ("check_out", "<="),
        }

        for key, (field_name, operator) in date_filters.items():
            if key in kwargs:
                domain.append((field_name, operator, kwargs[key]))

        bookings = self.search(domain)
        return self.prepare_booking_response(bookings)

    def prepare_guest_details(self, partner):
        return {
            "firstname": partner.name.split(" ")[0],
            "lastname": " ".join(partner.name.split(" ")[1:]) or "",
            "email": partner.email or "",
            "phone": partner.phone or "",
            "address": partner.street or "",
            "state": partner.state_id.name or "",
            "city": partner.city or "",
            "zip": partner.zip or "",
            "state_code": partner.state_id.code or "",
            "country_code": partner.country_id.code or "",
        }

    def prepare_price_details(self, booking):
        return {
            "total_price_with_tax": booking.total_amount,
            "total_tax": booking.tax_amount,
        }

    def prepare_discounts(self, sale_orders):
        return [
            {
                "name": discount.name,
                "code": discount.code,
                "value": discount.value,
                "type": discount.type,
            }
            for discount in sale_orders.mapped("discount_ids")
        ]

    def prepare_taxes(self, taxes, price):
        return [
            {
                "name": tax.name,
                "rate": tax.amount if tax.amount_type == "percent" else None,
                "total_tax": (
                    (price * tax.amount / 100)
                    if tax.amount_type == "percent"
                    else tax.amount
                ),
            }
            for tax in taxes
        ]

    def prepare_services(self, services):
        return [
            {
                "name": service.service_id.name,
                "quantity": 1,
                "total_price_with_tax": service.amount,
                "price_per_unit": service.amount,
                "taxes": [],
            }
            for service in services
        ]

    def prepare_rooms(self, booking_lines):
        return [
            {
                "id_room_type": line.product_tmpl_id.id,
                "check_in_date": line.booking_id.check_in.strftime("%Y-%m-%d %H:%M:%S"),
                "check_out_date": line.booking_id.check_out.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "number_of_rooms": line.booking_days,
                "total_price_with_tax": line.subtotal_price,
                "total_tax": line.taxed_price,
                "occupancy": {
                    "adults": len(
                        line.guest_info_ids.filtered(
                            lambda self: self.is_adult)
                    ),
                    "children": len(
                        line.guest_info_ids.filtered(
                            lambda self: not self.is_adult)
                    ),
                    "children_ages": line.guest_info_ids.filtered(
                        lambda self: not self.is_adult
                    ).mapped("age"),
                    "infants": 1,
                },
                "services": self.prepare_services(line.hotel_service_lines),
                "taxes": self.prepare_taxes(line.tax_ids, line.subtotal_price),
            }
            for line in booking_lines
        ]

    def prepare_booking_response(self, bookings):
        """
        Prepares the final response for the bookings.
        For -> API-endpoint: /api/bookings
        """
        booking_data = []
        for booking in bookings:
            if booking.status_bar == "cancel":
                booking_status = "cancelled"
            elif booking.need_to_sync:
                booking_status = "modified"
            else:
                booking_status = "new"
            booking_data.append(
                {
                    "id_booking": booking.id if booking else "",
                    "id_property": booking.hotel_id.id if booking.hotel_id else "",
                    "currency": booking.currency_id.name if booking.currency_id else "",
                    "booking_status": booking_status,
                    "modification_date": (
                        booking.write_date.strftime("%Y-%m-%d %H:%M:%S")
                        if booking.write_date
                        else booking.create_date.strftime("%Y-%m-%d %H:%M:%S")
                    ),
                    "payment_status": booking.order_id.invoice_status or "",
                    "source": dict(booking._fields["booking_reference"].selection).get(
                        booking.booking_reference, ""
                    ),
                    "booking_date": booking.create_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "remark": booking.cancellation_reason or "",
                    "number_of_rooms": len(booking.booking_line_ids),
                    "guest_detail": self.prepare_guest_details(booking.partner_id),
                    "price_details": self.prepare_price_details(booking),
                    "room_bookings": self.prepare_room_bookings(
                        booking.booking_line_ids
                    ),
                }
            )
        return booking_data

    def prepare_room_bookings(self, booking_lines):
        """
        Prepares room_booking data with rooms inside it. This is as per the Qlo API format.
        Returns -> A list of room_booking data.
        """
        dict_for_room_bookings = {}

        for line in booking_lines:
            key = line.product_tmpl_id.id
            dict_for_room_bookings.setdefault(key, []).append(line)

        room_bookings = []
        for room_type_id, lines in dict_for_room_bookings.items():
            first_line_data = lines[0]
            id_rate_plan = ""

            check_in_date = (
                first_line_data.booking_id.check_in.strftime(
                    "%Y-%m-%d %H:%M:%S")
                if first_line_data.booking_id.check_in
                else ""
            )
            check_out_date = (
                first_line_data.booking_id.check_out.strftime(
                    "%Y-%m-%d %H:%M:%S")
                if first_line_data.booking_id.check_out
                else ""
            )

            number_of_rooms = len(lines)
            total_price_with_tax = sum(line.subtotal_price for line in lines)
            total_tax = sum(line.taxed_price for line in lines)

            rooms = []
            for line in lines:
                room = {
                    "total_price_with_tax": line.subtotal_price,
                    "total_tax": line.taxed_price,
                    "occupancy": {
                        "adults": len(
                            line.guest_info_ids.filtered(lambda r: r.is_adult)
                        ),
                        "children": len(
                            line.guest_info_ids.filtered(
                                lambda r: not r.is_adult)
                        ),
                        "children_ages": line.guest_info_ids.filtered(
                            lambda r: not r.is_adult
                        ).mapped("age"),
                        "infants": 1,
                    },
                    "services": self.prepare_services(line.hotel_service_lines),
                    "taxes": self.prepare_taxes(line.tax_ids, line.subtotal_price),
                }
                rooms.append(room)

            room_booking = {
                "id_room_type": room_type_id,
                "id_rate_plan": id_rate_plan,
                "check_in_date": check_in_date,
                "check_out_date": check_out_date,
                "number_of_rooms": number_of_rooms,
                "total_price_with_tax": total_price_with_tax,
                "total_tax": total_tax,
                "rooms": rooms,
            }
            room_bookings.append(room_booking)

        return room_bookings

    def process_booking_data(self, booking_data):
        """
        Process the booking data received from the qlo end.
        Arguments:
            booking_data: Data dictionary that contains details (from request).
        Returns:
            The ID of the newly created booking record or an acknowledgement.
        """
        if booking_data.get("booking_status") == "new":
            return self.create_or_modify_booking(booking_data)
        elif booking_data.get("booking_status") == "cancelled":
            return self.cancel_existing_booking(booking_data)
        elif booking_data.get("booking_status") == "modified":
            return self.create_or_modify_booking(booking_data, "edit")

    def cancel_existing_booking(self, booking_data):
        """
        Process the booking data received from the qlo end.
        Arguments:
            booking_data: Data dictionary that contains details (from request).
        Returns:
            The ID of the cancelled bookings.
        """
        if booking_data.get("id_booking"):
            odoo_booking = self.browse(int(booking_data["id_booking"]))
            if odoo_booking.exists():
                odoo_booking.cancel_booking(
                    "Booking cancelled from the qlo end")
                return odoo_booking.id
        return False

    def get_guest_details(self, info):
        """
        Prepare the booking lines for the sale order.
        Arguments:
        booking_data: Data dictionary that contains details for the booking(from request).
        :returns:           A list with a dictionary.
        """
        guests = []
        if info.get("adults", "") != "":
            guests += [
                (
                    0,
                    0,
                    {
                        "name": f"Adult{str(i)}",
                        "age": 20,
                    },
                )
                for i in range(int(info.get("adults", 1)))
            ]
        if info.get("children", "") != "":
            guests += [
                (
                    0,
                    0,
                    {
                        "name": f"Children{str(i)}",
                        "age": 15,
                    },
                )
                for i in range(int(info.get("children", 1)))
            ]
        return guests

    def get_tax_details(self, product, taxes):
        """
        Prepare the booking lines for the sale order.
        Arguments:
        booking_data: Data dictionary that contains details for the booking(from request).
        :returns:           A list with a dictionary.
        """
        tax_ids = []
        for tax in taxes:
            product_tax = product.taxes_id.filtered(
                lambda t: t.name == tax.get("name", "")
            )
            if product_tax:
                tax_ids.append(product_tax.id)
        return [(6, 0, tax_ids)]

    def get_service_id(self, service_name):
        """Create service if not exists

        Args:
            service_name (string): service name
        :Returns:
            Service Id
        """
        Service = self.env["hotel.service"]
        hotel_service = Service.search(
            [("name", "=", service_name), ("service_type", "=", "paid")], limit=1
        )
        if hotel_service:
            return hotel_service.id
        else:
            return Service.create({"name": service_name, "service_type": "paid"}).id

    def get_services_details(self, services):
        """
        Prepare the services lines for the booking lines.
        Arguments:
        booking_data: Data dictionary that contains details for the booking(from request).
        :returns:           A list with a dictionary.
        """
        return [
            (
                0,
                0,
                {
                    "service_id": self.get_service_id(service.get("name", False)),
                    "amount": service.get("total_price_with_tax", 0),
                },
            )
            for service in services
        ]

    def _prepare_booking_lines(self, booking_data):
        """
        Prepare the booking lines for the hotel bookings.
        Arguments:
            booking_data: Data dictionary that contains details for the booking(from request).
        :returns:           A list with a dictionary.
        """
        booking_lines = []
        room_bookings = booking_data.get("room_bookings", [])
        for room_booking in room_bookings:
            room_type = self.env["product.template"].browse(
                int(room_booking.get("id_room_type"))
            )
            if room_type.product_variant_count >= room_booking.get("number_of_rooms", 1):
                for index, room in enumerate(room_booking.get("rooms", [])):
                    booking_line = (
                        0,
                        0,
                        {
                            "product_id": room_type.product_variant_ids[index].id,
                            "price": room_type.product_variant_ids[index].lst_price,
                            "tax_ids": self.get_tax_details(
                                room_type.product_variant_ids[index],
                                room.get("taxes", []),
                            ),
                            "subtotal_price": room.get("total_tax", 0),
                            "guest_info_ids": self.get_guest_details(
                                room.get("occupancy", {})
                            ),
                            "hotel_service_lines": self.get_services_details(room.get("services", [])),
                        },
                    )
                    booking_lines.append(booking_line)
        return booking_lines

    def create_or_modify_booking(self, booking_data, mode="create"):
        """
        Creates a new booking record from the provided data.
        Arguments:
            booking_data: Data dictionary that contains details for the new booking(from request).
        Returns:
            The ID of the newly created booking record.
        """

        partner_data = booking_data.get("guest_detail", {})
        room_data = booking_data.get("room_bookings", [])[0].get("rooms", [])
        booking_date = booking_data.get("booking_date")
        price_details = booking_data.get("price_details", {})

        partner = (
            self.env["res.partner"]
            .sudo()
            .search(
                [
                    (
                        "name",
                        "=",
                        f"{partner_data.get('firstname', '')} {partner_data.get('lastname', '')}".strip(
                        ),
                    ),
                    ("email", "=", partner_data.get("email")),
                ],
                limit=1,
            )
        )

        if price_details:
            total_amount = price_details.get("total_price_with_tax")
            tax_amount = price_details.get("total_tax")
        else:
            raise UserError("Price Details are missing")

        if partner:
            partner.write(
                {
                    "street": partner_data.get("address"),
                    "city": partner_data.get("city"),
                    "state_id": self.env["res.country.state"]
                    .sudo()
                    .search([("name", "=", partner_data.get("state"))], limit=1)
                    .id
                    or False,
                    "zip": partner_data.get("zip"),
                    "country_id": self.env["res.country"]
                    .sudo()
                    .search([("code", "=", partner_data.get("country_code"))], limit=1)
                    .id
                    or False,
                }
            )
        else:
            partner = (
                self.env["res.partner"]
                .sudo()
                .create(
                    {
                        "name": f"{partner_data.get('firstname', '')} {partner_data.get('lastname', '')}".strip(),
                        "email": partner_data.get("email"),
                        "phone": partner_data.get("phone"),
                        "street": partner_data.get("address"),
                        "city": partner_data.get("city"),
                        "state_id": self.env["res.country.state"]
                        .sudo()
                        .search([("name", "=", partner_data.get("state"))], limit=1)
                        .id
                        or False,
                        "zip": partner_data.get("zip"),
                        "country_id": self.env["res.country"]
                        .sudo()
                        .search(
                            [("code", "=", partner_data.get("country_code"))], limit=1
                        )
                        .id
                        or False,
                    }
                )
            )

        check_in = check_out = False
        if room_data:
            check_in = datetime.strptime(
                booking_data.get("room_bookings", [])[0].get("check_in_date"),
                "%Y-%m-%d",
            )
            check_out = datetime.strptime(
                booking_data.get("room_bookings", [])[0].get("check_out_date"),
                "%Y-%m-%d",
            )
        pricelist = (
            self.env["product.pricelist"]
            .sudo()
            .search([("currency_id.name", "=", booking_data.get("currency"))], limit=1)
        )
        if not pricelist:
            pricelist = self._default_pricelist_id()

        if not pricelist:
            raise ValueError(
                "-> No active pricelist found. Ensure a pricelist is configured in the system."
            )
        hotel_id = (
            self.env["hotel.hotels"].browse(
                booking_data.get("id_property")).exists()
        )
        data = {
            "hotel_id": booking_data.get("id_property") if hotel_id else False,
            "booking_reference": "other",
            "origin": booking_data.get("source", ""),
            "description": booking_data.get("remark"),
            "check_in": check_in,
            "check_out": check_out,
            "booking_date": datetime.strptime(booking_date, "%Y-%m-%d %H:%M:%S"),
            "partner_id": partner.id,
            "pricelist_id": pricelist.id,
            "total_amount": total_amount or False,
            "tax_amount": tax_amount or False,
            "need_to_sync": True,
        }
        if mode == "create":
            lines = self._prepare_booking_lines(booking_data)
            data.update({"booking_line_ids": lines})
            odoo_booking = self.create(data)
            odoo_booking.with_context(
                bypass_checkin_checkout=True
            ).action_confirm_booking()
        else:
            odoo_booking = self.browse(int(booking_data["id_booking"]))
            if odoo_booking.exists() and odoo_booking.status_bar not in [
                "checkout",
                "cancel",
            ]:
                odoo_booking.write(data)

        return odoo_booking.id if odoo_booking else False
