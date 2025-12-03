# -*- coding: utf-8 -*-
##########################################################################
#
#    Copyright (c) 2015-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#
##########################################################################

import logging

from odoo import models, fields, _, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HotelHotels(models.Model):
    _inherit = "hotel.hotels"

    def get_all_hotels_data(self):
        """
        Returns required data of every record of published hotels
        """
        hotels = self.search([("is_published", "=", True)])
        hotel_data = []

        for hotel in hotels:
            partner = hotel.partner_id
            hotel_data.append(
                {
                    "id": str(hotel.id),
                    "name": hotel.name,
                    "property_type": "hotel",
                    "description": hotel.description or "",
                    "email": partner.email or "",
                    "phone": partner.phone or "",
                    "currency": hotel.currency_id.name,
                    "country_code": partner.country_id.code or "",
                    "state": partner.state_id.name or "",
                    "city": partner.city or "",
                    "address1": partner.street or "",
                    "address2": partner.street2 or "",
                    "zip_code": partner.zip or "",
                    "latitude": partner.partner_latitude or "",
                    "longitude": partner.partner_longitude or "",
                    "timezone": hotel.default_timezone or "",
                }
            )
        return hotel_data

    def get_hotel_room_types(self):
        self.ensure_one()
        """
        Returns required data of every rooms of the published hotels
        """
        return [
            {
                "id": str(room.id),
                "id_property": str(self.id),
                "name": room.name,
                "total_rooms": room.product_variant_count,
                "base_occupancy": room.base_occupancy,
                "max_adults": room.max_adult,
                "max_children": room.max_child,
                "max_infants": room.max_infants,
            }
            for room in self.room_ids
        ]
