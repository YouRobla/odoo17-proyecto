# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#
#################################################################################
import json
import werkzeug
import werkzeug.utils
import werkzeug.urls
import logging

from odoo.http import request, Controller, route


_logger = logging.getLogger(__name__)


class HotelRestWebServices(Controller):

    def _response(self, response, ctype="json"):
        body = {}

        if ctype == "json":
            mime = "application/json; charset=utf-8"

            try:
                body = json.dumps(response, default=lambda o: o.__dict__)
            except Exception as e:
                response["responseCode"] = 500
                body["message"] = "ERROR: %r" % (e)
                body["success"] = False
                body = json.dumps(body, default=lambda o: o.__dict__)

        headers = [
            ("pms_token", "9yCLFKSS52OQ"),
            ("Content-Type", mime),
            ("Content-Length", len(body)),
        ]
        return werkzeug.wrappers.Response(body, headers=headers)

    def _authenticate(self, **kwargs):
        if "api_key" in kwargs.keys():
            api_key = kwargs.get("api_key")
        elif request.httprequest.headers.get("api_key"):
            api_key = request.httprequest.headers.get("api_key") or None
        else:
            api_key = False
        RestAPI = request.env["hotel.rest.api"].sudo()
        response = RestAPI._validate(api_key)
        response.update(kwargs)
        return response

    @route(["/api", "/api/test_connection"], csrf=False, type="http", auth="none")
    def check_api_status(self, **kwargs):
        """HTTP METHOD : request.httprequest.method"""
        response = self._authenticate(**kwargs)
        if response.get("success"):
            data = response
            return self._response(data, "json")
        else:
            headers = [
                (
                    "WWW-Authenticate",
                    'Basic realm="Welcome to Hotel WebService, please enter the authentication key as the login. No password is required."',
                )
            ]
            return werkzeug.wrappers.Response(
                "401 Unauthorized %r" % request.httprequest.authorization,
                status=401,
                headers=headers,
            )

    @route("/api/properties", csrf=False, type="http", auth="public", methods=["GET"])
    def get_properties(self, **kwargs):
        """
        API Endpoint: /api/properties
        Fetches all data of Hotels and returns as JSON
        """
        response = self._authenticate(**kwargs)
        if response.get("success"):
            try:
                hotels = request.env["hotel.hotels"].sudo().get_all_hotels_data()

                data = {
                    "responseCode": 200,
                    "message": "Data fetched successfully",
                    "data": hotels,
                    "success": True,
                }
                return self._response(data)
            except Exception as e:
                error_response = {
                    "responseCode": 500,
                    "message": f"An error occurred: {e}",
                    "success": False,
                }
                return self._response(error_response)
        else:
            headers = [
                (
                    "WWW-Authenticate",
                    'Basic realm="Welcome to Hotel WebService, please enter the authentication key as the login. No password is required."',
                )
            ]
            return werkzeug.wrappers.Response(
                "401 Unauthorized %r" % request.httprequest.authorization,
                status=401,
                headers=headers,
            )

    @route("/api/room_types", csrf=False, type="http", auth="public", methods=["GET"])
    def get_hotel_room_types(self, **kwargs):
        """
        API Endpoint: /api/properties
        Fetches all data of Hotels and returns as JSON
        """
        response = self._authenticate(**kwargs)
        if response.get("success"):
            try:
                if kwargs.get("filter[id_property]", False):
                    rooms = (
                        request.env["hotel.hotels"]
                        .sudo()
                        .browse(int(kwargs["filter[id_property]"]))
                        .get_hotel_room_types()
                    )

                    data = {
                        "responseCode": 200,
                        "message": "Data fetched successfully",
                        "data": rooms,
                        "success": True,
                    }
                else:
                    data = {
                        "responseCode": 200,
                        "message": "Please provide the property id in the correct format. For Exp.> https://example.com/api/room_types?filter[id_property]=PROPERTY_ID",
                        "data": [],
                        "success": False,
                    }
                return self._response(data)
            except Exception as e:
                error_response = {
                    "responseCode": 500,
                    "message": f"An error occurred: {e}",
                    "success": False,
                }
                return self._response(error_response)
        else:
            headers = [
                (
                    "WWW-Authenticate",
                    'Basic realm="Welcome to Hotel WebService, please enter the authentication key as the login. No password is required."',
                )
            ]
            return werkzeug.wrappers.Response(
                "401 Unauthorized %r" % request.httprequest.authorization,
                status=401,
                headers=headers,
            )

    @route("/api/bookings", csrf=False, type="http", auth="public", methods=["GET"])
    def get_bookings(self, **kwargs):
        """
        API Endpoint: /api/bookings
        Fetches booking details based on query parameters and returns JSON response.
        """
        response = self._authenticate(**kwargs)
        if response.get("success"):
            try:
                bookings = (
                    request.env["hotel.booking"].sudo().get_filtered_bookings(**kwargs)
                )
                data = {
                    "responseCode": 200,
                    "message": "Data fetched successfully",
                    "data": bookings,
                    "success": True,
                }
                return self._response(data)
            except Exception as e:
                error_response = {
                    "responseCode": 500,
                    "message": f"An error occurred: {e}",
                    "success": False,
                }
                return self._response(error_response)
        else:
            return werkzeug.wrappers.Response(
                "401 Unauthorized",
                status=401,
                headers=[("WWW-Authenticate", 'Basic realm="Hotel WebService"')],
            )

    @route(
        "/api/booking_notification",
        csrf=False,
        type="http",
        auth="public",
        methods=["POST"],
    )
    def create_booking(self, **kwargs):
        """
        API Endpoint: /api/bookings (POST)
        Creates a new booking based on the provided data and returns the newly created booking's ID.
        """
        response = self._authenticate(**kwargs)
        if response.get("success"):
            try:
                data = json.loads(request.httprequest.data)
                if not data:
                    return self._response(
                        {
                            "responseCode": 400,
                            "message": "Missing booking data.",
                            "success": False,
                        }
                    )

                booking_id = (
                    request.env["hotel.booking"].sudo().process_booking_data(data)
                )

                if not booking_id:
                    message = "Booking has not found for the corresponding booking id at the odoo end"
                    data = []
                else:
                    message = (
                        "Booking data have been processed successfully at the odoo end"
                    )
                    data = {"id_pms_booking": booking_id}
                return self._response(
                    {
                        "responseCode": 200,
                        "message": message,
                        "data": data,
                        "success": True,
                    }
                )

            except Exception as e:
                error_response = {
                    "responseCode": 500,
                    "message": f"An error occurred: {e}",
                    "success": False,
                }
                return self._response(error_response)

        else:
            return werkzeug.wrappers.Response(
                "401 Unauthorized",
                status=401,
                headers=[("WWW-Authenticate", 'Basic realm="Hotel WebService"')],
            )
