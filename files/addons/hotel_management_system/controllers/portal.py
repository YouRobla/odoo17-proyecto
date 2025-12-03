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
from odoo import http, _
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class CustomerPortal(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "booking_count" in counters:
            partner = request.env.user.partner_id
            HotelBooking = request.env["hotel.booking"]
            booking_count = HotelBooking.search_count(
                [("partner_id", "in", [partner.id]),
                 ("status_bar", "in", ["allot"])]
            )
            values.update(
                {
                    "booking_count": 0 if not booking_count else booking_count,
                }
            )
        return values

    @http.route(
        ["/my/booking/order/<int:page>"], type="http", auth="user", website=True, sitemap=True
    )
    def my_booking_order(self, page=0, **kw):
        if page:
            sale_order = request.env["sale.order"].browse(page)
            return request.render(
                "hotel_management_system.sale_booking_order",
                {
                    "sale_order": sale_order,
                    "report_type": "html",
                    "page_name": "my_booking",
                },
            )

    @http.route(
        ["/my/booking", "/my/booking/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
        sitemap=False
    )
    def portal_my_booking(self, page=0, sortby=None, **kw):
        values = self._prepare_portal_layout_values()
        HotelBooking = request.env["hotel.booking"]
        partner = request.env.user.partner_id
        domain = [("partner_id", "in", [partner.id]),
                  ("status_bar", "in", ["allot"])]

        searchbar_sortings = {
            "date": {"label": _("Booking Date"), "order": "check_in desc"},
            "reference": {"label": _("Reference No"), "order": "sequence_id"},
            "stage": {"label": _("Status"), "order": "status_bar"},
        }

        if not sortby:
            sortby = "date"
        sort_order = searchbar_sortings[sortby]["order"]

        quotation_count = HotelBooking.search_count(domain)

        pager = portal_pager(
            url="/my/booking",
            url_args={"sortby": sortby},
            total=quotation_count,
            page=page,
            step=self._items_per_page,
        )

        # search the count to display, according to the pager data
        bookings = HotelBooking.search(
            domain, order=sort_order, limit=self._items_per_page, offset=pager["offset"]
        )
        request.session["my_quotations_history"] = bookings.ids[:100]
        if page:
            table_active = True
        else:
            table_active = False
        values.update(
            {
                "bookings": bookings.sudo(),
                "page_name": "my_booking",
                "pager": pager,
                "table_active": table_active,
                "default_url": "/my/booking",
                "searchbar_sortings": searchbar_sortings,
                "sortby": sortby,
            }
        )
        return request.render("hotel_management_system.portal_my_booking", values)
