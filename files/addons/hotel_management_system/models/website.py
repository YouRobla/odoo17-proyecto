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
from datetime import datetime
import logging

from odoo import api, fields, models, _lt
from odoo.http import request
from odoo.addons.website.models import ir_http

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = "website"

    def apply_cron(self):
        website_id = self.get_current_website()
        website_id.cron_id = self.env.ref(
            "hotel_management_system.ir_cron_reset_trending_product"
        )

    website_homepage_product_ids = fields.Many2many(
        "product.template", relation="home_page_product_rel", string="Homepage Product"
    )
    checkout_hours = fields.Float(
        string="Checkout Hours", default=12.00,
    )
    hotel_product_variant = fields.Many2many(
        "product.template",
        relation="trending_product_rel",
        string="Trending Products",
    )
    cron_id = fields.Many2one(
        string="Cron", comodel_name="ir.cron", readonly=False)
    interval_number = fields.Integer(related="cron_id.interval_number")
    interval_type = fields.Selection(related="cron_id.interval_type")
    max_trending_limit = fields.Integer("Max Trending Limit")

    def sale_product_domain(self):
        is_frontend = (
            ir_http.get_request_website()
        )
        subdomain = []

        if is_frontend:
            if request.params.get("check_in", False) and request.params.get("check_out", False):
                subdomain = [
                    ("is_room_type", "=", True),
                    ('max_adult', '>=', int(request.params.get("adult", 0) or 0)),
                    ('max_child', '>=', int(request.params.get("child", 0) or 0)),
                ]

                check_in = datetime.strptime(
                    request.params.get("check_in"), "%m/%d/%Y"
                )
                check_out = datetime.strptime(
                    request.params.get("check_out"), "%m/%d/%Y"
                )

                booking = request.env["hotel.booking"].search([])
                all_room_type_products = request.env["product.product"].search(
                    subdomain)
                filtered_booking = booking.filter_booking_based_on_date(
                    check_in, check_out)
                available_rooms = (all_room_type_products - filtered_booking.mapped(
                    "booking_line_ids.product_id")).mapped("product_tmpl_id")
                domain = [("id", "in", available_rooms.ids)]
                subdomain = ["&"] + subdomain + domain

        if subdomain:
            return ["&"] + super(Website, self).sale_product_domain() + subdomain
        else:
            return super(Website, self).sale_product_domain()

    @api.model
    def hotel_management_system_snippet_data(self):
        default_website = self.env["website"].search([], limit=1)
        room_type_product = (
            self.env["product.template"]
            .sudo()
            .search([("is_room_type", "=", True), ("active", "=", True)], limit=12)
        )
        default_website.website_homepage_product_ids = room_type_product

    @api.model
    def get_wire_transfer(self):
        try:
            wire_transfer = self.env.ref(
                "payment.payment_provider_transfer", raise_if_not_found=False
            )
            pay_method = self.env.ref(
                "hotel_management_system.payment_method_hotel_demo",
                raise_if_not_found=False,
            )
            if wire_transfer.module_id.state != "installed":
                wire_transfer.module_id.button_install()
                return (
                    wire_transfer.write(
                        {
                            "name": "Pay at Hotel",
                            "state": "test",
                            "website_id": False,
                            "is_published": True,
                            "payment_method_ids": [(4, pay_method.id)],
                        }
                    )
                    if wire_transfer
                    else False
                )
            return (
                wire_transfer.write(
                    {
                        "name": "Pay at Hotel",
                        "is_published": True,
                        "payment_method_ids": [(4, pay_method.id)],
                    }
                )
                if wire_transfer
                else False
            )
        except Exception as e:
            _logger.info("Couldn't install Wire Transfer due to an error.")
            _logger.info(e)
            return False

    def _get_checkout_steps(self, current_step=None):
        res = super()._get_checkout_steps(current_step=current_step)
        sale_order = request.website.sale_get_order()
        if not sale_order:
            return res

        has_room_product = any(
            line.product_id.is_room_type for line in sale_order.order_line
        )
        if has_room_product and isinstance(res, list):
            res.insert(
                1,
                (
                    ["hotel_management_system.guest_info_page"],
                    {
                        "name": _lt("Guest Info"),
                        "current_href": "/guest/page",
                        "main_button": _lt("Confirm"),
                        "main_button_href": "/shop/confirm_order",
                        "back_button": _lt("Back to cart"),
                        "back_button_href": "/shop/cart",
                    },
                ),
            )
        return res
