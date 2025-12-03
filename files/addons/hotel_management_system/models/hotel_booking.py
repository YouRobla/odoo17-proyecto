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
import datetime as dt
import uuid
from datetime import datetime, timedelta
import pytz
from collections import defaultdict

from odoo import fields, models, api, _
from odoo.http import request
from odoo.exceptions import ValidationError, UserError

class HotelBooking(models.Model):
    _name = "hotel.booking"
    _inherit = ["rating.mixin", "mail.thread", "mail.activity.mixin"]
    _description = "Hotel Booking Management"

    _rec_name = "sequence_id"

    """ This method is called from a cron job.
        It is used to create house keeping record based on housekeeping config.
    """
    def _auto_create_house_keeping(self):
        if self.env["ir.config_parameter"].sudo().get_param(
            "hotel_management_system.housekeeping_config"
        ) in ["daily", "both"]:
            records = self.search(["status_bar", "=", "allot"])
            for rec in records:
                rec.create_housekeeping()

    def _default_pricelist_id(self):
        res = self.env["product.pricelist"].search(
            ["|", ("company_id", "=", False), ("company_id", "=", self.env.company.id)],
            limit=1,
        )
        return res

    def _default_access_token(self):
        return uuid.uuid4().hex

    def action_add_rooms(self):
        self.ensure_one()
        booking = self.env["hotel.booking"].search([])
        product_ids = self.env["product.product"].search([('product_tmpl_id.hotel_id', '!=', self.hotel_id.id)])

        for line in booking:
            if line.filter_booking_based_on_date(self.check_in, self.check_out):
                product_ids += line.mapped("booking_line_ids.product_id")

        return {
            'name': 'Add Rooms',
            'type': 'ir.actions.act_window',
            'res_model': 'hotel.booking.line',
            'view_mode': 'form',
            'view_id': self.env.ref('hotel_management_system.custom_hotel_booking_line_view_form').id,
            'target': 'new',
            'context': {
                'default_booking_id': self.id,
                'default_booking_days': self.booking_days,
                'default_product_ids': product_ids.ids,
            }
        }

    @api.onchange('hotel_id')
    def _onchange_hotel_id(self):
        if self.booking_line_ids:
            raise ValidationError('Cannot change the Hotel if already created booking lines for a different Hotel, Please clear the lines first to change the Hotel')

    invoice = fields.Char()
    invoice_ids = fields.One2many("account.move", "hotel_booking_id", string="Invoices")
    invoice_count = fields.Integer(compute="compute_invoice_count")
    sequence_id = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("New"),
    )
    image_1920 = fields.Image(related="partner_id.image_1920")
    sale_order_ids = fields.One2many("sale.order", "booking_id", string="Sale Orders")
    user_id = fields.Many2one(
        "res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        tracking=True,
    )
    booking_generate = fields.Boolean("Booking Already Available")
    order_id = fields.Many2one("sale.order", "Sale Order")
    booking_line_ids = fields.One2many(
        "hotel.booking.line", "booking_id", string="Booking Line"
    )
    partner_id = fields.Many2one(
        "res.partner",
        "Guest Name",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    booking_date = fields.Datetime(
        "Booking Date",
        required=True,
        default=lambda self: fields.Datetime.now(),
        tracking=True,
        copy=False,
        help="Booking Date.",
    )
    check_in = fields.Datetime(
        "Check In",
        required=True,
        copy=False,
        default=lambda self: fields.Datetime.now(),
        tracking=True,
        help="Start date of the arrival.",
    )
    check_out = fields.Datetime(
        "Check Out", tracking=True, copy=False, help="End date of the departure."
    )
    status_bar = fields.Selection(
        [
            ("initial", "Draft"),
            ("confirm", "Confirm"),
            ("allot", "Room Allocated"),
            ("cancel", "Cancel"),
            ("checkout", "Checkout"),
        ],
        default="initial",
        copy=False,
        string="State",
        tracking=True,
    )
    booking_reference = fields.Selection(
        [
            ("sale_order", "Website"),
            ("manual", "Direct"),
            ("agent", "Via Agent"),
            ("other", "Other"),
        ],
        default="manual",
        copy=False,
        string="Source ",
        tracking=True,
    )
    origin = fields.Char("Origin", copy=False)
    pricelist_id = fields.Many2one(
        "product.pricelist",
        string="Pricelist",
        readonly=False,
        default=_default_pricelist_id,
        tracking=True,
    )
    currency_id = fields.Many2one(
        string="Currency",
        comodel_name='res.currency',
        compute='_compute_currency_id',
        store=True,
        precompute=True,
        ondelete='restrict',
        tracking=True,
    )
    amount_untaxed = fields.Monetary("Amount Untaxed", compute="_compute_actual_amount")
    total_amount = fields.Monetary("Total amount", tracking=True)
    booking_discount = fields.Monetary("Discount")
    tax_amount = fields.Monetary(string="Tax Amount", tracking=True)
    docs_ids = fields.One2many("hotel.document", "booking_id", string="Document")
    cancellation_reason = fields.Text("Booking Cancellation Reason ")
    is_show_create_invoice_btn = fields.Boolean(
        "Is show Create Button", compute="_compute_show_btn"
    )
    is_show_send_feedback_btn = fields.Boolean(
        "Is show Feedback Button", compute="_compute_show_feedback_btn"
    )
    show_create_bill_btn = fields.Boolean(
        "Show create bill button", compute="_compute_show_bill_btn"
    )
    hotel_id = fields.Many2one(
        "hotel.hotels",
        "Hotel",
        default=lambda self: self.env["hotel.hotels"].search([], limit=1),
        tracking=True,
    )
    
    hotel_service_lines = fields.One2many(
        "hotel.booking.service.line",
        "booking_id",
        string="Other Service Lines",
    )
    booking_days = fields.Integer(
        string="Days Book For",
        compute="_compute_booking_days",
        copy=False,
        tracking=True,
    )
    description = fields.Text("Remarks")

    def _compute_show_btn(self):
        is_show_create_invoice_btn = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.auto_invoice_gen")
        )
        for rec in self:
            rec.is_show_create_invoice_btn = is_show_create_invoice_btn

    def _compute_show_bill_btn(self):
        auto_bill_gen = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.auto_bill_gen")
        )
        for rec in self:
            rec.show_create_bill_btn = not auto_bill_gen

    via_agent = fields.Boolean("Via Agent")
    agent_id = fields.Many2one("res.partner", "Agent")
    commission_type = fields.Selection(
        [("fixed", "Fixed"), ("percentage", "Percentage")],
        default="fixed",
        string="Commission Type",
    )
    agent_commission_amount = fields.Float("Agent Commission Amount")
    agent_commission_percentage = fields.Float("Agent Commission Percentage (%)")
    agent_invoice_id = fields.Many2one(
        "account.move",
        string="Agent Bill",
        help="The vendor bill created for the agent.",
    )
    housekeeping_count = fields.Integer(
        "Housekeeping count", compute="count_housekeeping", store=True
    )

    access_token = fields.Char(
        "Invitation Token", default=_default_access_token, copy=False
    )

    # -=-=-=-=-=-=-=-=- Advance Payment Integration Start -=-=-=-=-=-=-=-=-=-
    payment_ids = fields.One2many(
        related="order_id.payment_ids",
        string="Payments",
        readonly=True
    )
    paid_amount = fields.Float(
        related="order_id.paid_amount",
        string="Paid Amount",
        readonly=True
    )
    total_payment = fields.Integer(
        related="order_id.total_payment",
        string="Total Payments",
        readonly=True
    )
    balance_amount = fields.Float(
        related="order_id.balance_amount",
        string="Balance Amount",
        readonly=True
    )

    def action_register_payment(self):
        self.ensure_one()
        sale_order = self.order_id
        if not sale_order:
            raise UserError(_("No Sale Order linked to this booking."))

        amount = sale_order.amount_total - sale_order.paid_amount
        journal = self.env["account.journal"].search([("type", "in", ["cash", "bank"])])

        return {
            "name": _("Advance Payment"),
            "res_model": "account.payment",
            "view_mode": "form",
            "views": [(self.env.ref("hotel_management_system.view_form_amount_payment").id, "form")],
            "context": {
                "default_amount": amount,
                "default_currency_id": sale_order.currency_id.id,
                "default_partner_id": sale_order.partner_id.id,
                "default_move_journal_types": ["bank", "cash"],
                "default_partner_type": "customer",
                "default_sale_order_id": sale_order.id,
                "default_suitable_journal_ids": journal.ids,
            },
            "target": "new",
            "type": "ir.actions.act_window",
        }
    
    def action_show_payment(self):
        self.ensure_one()
        sale_order = self.order_id
        if not sale_order:
            raise UserError(_("No Sale Order linked to this booking."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Payments"),
            "res_model": "account.payment",
            "domain": [("sale_order_id", "=", sale_order.id)],
            "view_mode": "tree,form",
            "target": "self",
        }
    # -=-=-=-=-=-=-=-=- Advance Payment Integration End -=-=-=-=-=-=-=-=-=-

    def send_feedback_btn(self):
        template_id = self.env.ref(
            "hotel_management_system.hotel_rating_request_email_template"
        )
        template_id.send_mail(self.id, force_send=True)

    def send_checkout_email(self):
        template_id = self.env.ref(
            "hotel_management_system.hotel_checkout_email_template"
        )
        template_id.send_mail(self.id, force_send=True)

    def _compute_show_feedback_btn(self):
        config = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.feedback_config")
        ) == "manual"
        for rec in self:
            rec.is_show_send_feedback_btn = config

    def get_feedback_url(self):
        try:
            website = self.env["website"].sudo().get_current_website()
            base_url = website.get_base_url()
        except:
            base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        url = f"{base_url}/feedback/{self.id}?access_token={self.access_token}"
        return url

    @api.depends("booking_line_ids.housekeeping_id")
    def count_housekeeping(self):
        for rec in self:
            rec.housekeeping_count = len(rec.booking_line_ids.mapped("housekeeping_id"))

    @api.onchange("via_agent")
    def _onchange_via_agent(self):
        """Setting booking_reference to 'agent' when via_agent is checked."""
        if self.via_agent:
            self.booking_reference = "agent"
        else:
            self.booking_reference = "manual"

    @api.onchange("check_in", "check_out")
    def _onchange_check_in_out(self):
        '''
        New Check-in and Check-out validations
        '''
        today = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        for order in self:   
            if order.check_out:
                if order.check_in and order.check_out < order.check_in:
                    raise UserError("Check-out date cannot be before Check-in date.")

    def get_dashboard_data(self, start_date, hotel_id=None):
        hotels = self.env["hotel.hotels"].search_read([], ['name'])
        room_domain = [("is_room_type", "=", True)]
        booking_domain = [("create_date", ">=", start_date)]

        if hotel_id:
            room_domain.append(("hotel_id", "=", hotel_id))
            booking_domain.append(("hotel_id", "=", hotel_id))

        rooms = self.env["product.template"].search_read(
            room_domain,
            ["display_name", "list_price", "product_website_description"]
        )
        bookings = self.search(booking_domain)

        today_date = datetime.today().date()
        last_week_start = today_date - timedelta(days=today_date.weekday() + 7)
        last_week_end = today_date - timedelta(days=today_date.weekday() + 1)

        # Initialize revenue data and currency symbol
        revenue_data = {"today": 0, "yesterday": 0, "last_week": 0}
        currency_symbol = next(
            (booking.currency_id.symbol for booking in bookings if booking.currency_id),
            None,
        )

        # Count the total revenue for today, yesterday, and last week
        for booking in bookings:
            if booking.status_bar not in ["cancel", "draft"]:
                check_in_date = fields.Date.from_string(booking.check_in)
                if check_in_date == today_date:
                    revenue_data["today"] += booking.total_amount
                elif check_in_date == today_date - timedelta(days=1):
                    revenue_data["yesterday"] += booking.total_amount
                elif last_week_start <= check_in_date <= last_week_end:
                    revenue_data["last_week"] += booking.total_amount

        # Count bookings per city
        city_booking_count = defaultdict(int)
        for booking in bookings:
            if booking.partner_id and booking.partner_id.state_id:
                city_booking_count[booking.partner_id.state_id.name] += 1

        # Generate map data
        map_data = [
            {
                "city": f"{booking.partner_id.state_id.name} ({city_booking_count[booking.partner_id.state_id.name]}) bookings",
                "latitude": booking.partner_id.partner_latitude,
                "longitude": booking.partner_id.partner_longitude,
            }
            for booking in bookings
            if booking.partner_id
            and booking.partner_id.city
            and booking.partner_id.partner_latitude
            and booking.partner_id.partner_longitude
        ]

        # Fetch top 5 partners based on booking count
        domain = [("partner_id", "!=", False)]
        if hotel_id:
            domain.append(("hotel_id", "=", hotel_id))

        top_partners = self.read_group(
            domain,
            ["partner_id"],
            ["partner_id"],
            orderby="partner_id_count desc",
            limit=5,
        )

        # Prepare top customers' data
        top_customers = [
            {
                "name": self.env["res.partner"].browse(data["partner_id"][0]).name,
                "steps": data["partner_id_count"],
                "pictureSettings": {
                    "src": f"/web/image/res.partner/{data['partner_id'][0]}/avatar_128"
                },
            }
            for data in top_partners
        ]

        return {
            "hotels": hotels,
            "rooms": rooms,
            "bookings": bookings.read(
                [
                    "status_bar",
                    "check_in",
                    "check_out",
                    "partner_id",
                    "total_amount",
                    "currency_id",
                    "booking_reference",
                ]
            ),
            "booking_ids": bookings.ids,
            "revenue": revenue_data,
            "currency_symbol": currency_symbol,
            "map_data": map_data,
            "top_customers": top_customers,
        }

    def action_add_service(self):
        return {
            "name": "Add Service",
            "type": "ir.actions.act_window",
            "res_model": "hotel.service.wizard",
            "view_id": self.env.ref(
                "hotel_management_system.view_hotel_service_wizard_form"
            ).id,
            "view_mode": "form",
            "target": "new",
            "context": {"default_booking_id": self.id},
        }

    def cancel_booking(self, cancellation_reason=""):
        for rec in self:
            rec.write(
                {"cancellation_reason": cancellation_reason, "status_bar": "cancel"}
            )
        template_id = self.env.ref("hotel_management_system.hotel_booking_cancel_id")
        cancel_config = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.send_on_cancel")
        )

        if cancel_config:
            template_id.send_mail(self.id, force_send=True)

    def allot_action(self):
        return {
            "name": "Add Required Documents",
            "type": "ir.actions.act_window",
            "res_model": "customer.document",
            "view_id": self.env.ref(
                "hotel_management_system.view_customer_doc_form"
            ).id,
            "view_mode": "form",
            "target": "new",
            "context": {"default_booking_id": self.id},
        }

    @api.depends("invoice_ids")
    def compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids.ids)

    def action_view_compute_bill(self):
        order_ids = self.env["sale.order"].search(
            [("booking_id", "=", self.id), ("state", "=", "sale")]
        )
        return {
            "name": "Booking Bill",
            "type": "ir.actions.act_window",
            "res_model": "booking.bill",
            "view_id": self.env.ref("hotel_management_system.view_compute_bill").id,
            "view_mode": "form",
            "target": "new",
            "context": {"order_list": (self.order_id | order_ids).ids},
        }

    def hotel_invoice_view(self):
        """Invoice View

        Returns
        -------
        Open View in tree mode
        """
        invoices = (
            self.env["account.move"].sudo().search([("id", "in", self.invoice_ids.ids)])
        )
        invoice_len = len(invoices.ids)
        view_mode = ""
        action_dict = {
            "name": "Invoices",
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": view_mode,
            "target": "current",
        }
        if invoice_len > 1:
            view_mode = "tree,form"
            action_dict.update(
                {"domain": [("id", "in", self.invoice_ids.ids)], "view_mode": view_mode}
            )
        else:
            view_mode = "form"
            form_view = [(self.env.ref("account.view_move_form").id, "form")]
            action_dict.update({"views": form_view, "res_id": invoices.id})
        return action_dict

    def action_sale_order(self):
        return {
            "name": "Sale Order",
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "tree,form",
            "domain": [
                (
                    "id",
                    "in",
                    (
                        self.sale_order_ids.ids + [self.order_id.id]
                        if self.order_id
                        else self.sale_order_ids.ids
                    ),
                )
            ],
            "target": "current",
        }

    def filter_booking_based_on_date(self, check_in, check_out):
        if not (check_in and check_out):
            raise ValidationError(
                _("Please fill the Check in and Check out Details !!")
            )
        check_in = check_in.date()
        check_out = check_out.date()
        return self.filtered(
            lambda r: (
                r
                if r.status_bar not in ("cancel", "checkout")
                and (
                    (r.check_in).date() == check_in
                    or (
                        (r.check_in).date() <= check_in
                        and (r.check_out).date() > check_in
                    )
                    or (
                        (r.check_in).date() <= check_in
                        and (r.check_out).date() > check_in
                    )
                    or (
                        (
                            (r.check_in).date() >= check_in
                            and (r.check_in).date() <= check_out
                        )
                        or (
                            (
                                (r.check_in).date() <= check_in
                                and (r.check_out).date() <= check_out
                            )
                            and (r.check_out).date() > check_in
                        )
                        or (
                            (r.check_in).date() <= check_out
                            and (r.check_out).date() > check_in
                        )
                    )
                )
                else None
            )
        )

    def _check_validity_check_in_check_out_booking(self):
        """verifies if check_in is earlier than check_out."""
        for booking in self:
            if booking.check_in and booking.check_in < fields.Datetime.today():
                raise ValidationError(
                    _('"Check In" time cannot be earlier than Today time.')
                )
            if booking.check_in and booking.check_out:
                if booking.check_out <= booking.check_in:
                    raise ValidationError(
                        _('"Check Out" time cannot be earlier than "Check In" time.')
                    )

    def add_rooms_with_date_check(self):
        self._check_validity_check_in_check_out_booking()
        action_name = self.env.context.get("action_name", False)
        if not action_name:
            return False
        action = self.env["ir.actions.act_window"]._for_xml_id(
            f"hotel_management_system.{action_name}"
        )
        return action

    @api.model
    def fetch_data_for_dashboard(self, **kwargs):
        """fetch data for dashboard reload"""

        fetch_data = {}
        product = self.env["product.product"]
        booking = self.env["hotel.booking"]
        room_type_product = product.search(
            [("is_room_type", "=", True), ("active", "=", True)]
        )

        today_date = datetime.combine(fields.Date.today(), datetime.min.time())
        
        scale = kwargs.get('scale', 'today')
        if scale == 'today':
            start_date = today_date
            end_date = today_date + timedelta(days=1)
        elif scale == 'week':
            start_date = today_date - timedelta(days=today_date.weekday())
            end_date = start_date + timedelta(weeks=1)
        elif scale == 'month':
            start_date = datetime(today_date.year, today_date.month, 1)
            end_date = (start_date + timedelta(days=31)).replace(day=1)
        elif scale == 'year':
            start_date = datetime(today_date.year, 1, 1)
            end_date = datetime(today_date.year + 1, 1, 1)
        else:
            start_date = today_date
            end_date = today_date + timedelta(days=1)

        # Fetching bookings based on the scale
        today_booking = booking.search(
            [
                ("check_out", ">", start_date.date()),
                ("check_in", "<=", end_date),
                ("status_bar", "not in", ["initial", "checkout"]),
            ]
        )

        booked_room = today_booking.mapped("booking_line_ids.product_id")
        available_rooms = room_type_product - booked_room

        fetch_data.update(
            {
                "booked_room": len(booked_room),
                "available_rooms": len(available_rooms),
                "booked_room_ids": booked_room.ids,
            }
        )

        room_data = (
            self.env["product.template"]
            .sudo()
            .search([["is_room_type", "=", True]])
            .read(["name", "product_variant_count"])
        )

        # Check-ins and check-outs for the selected time range
        current_date_check_in = self.search(
            [
                ("check_in", ">=", start_date),
                ("check_in", "<", end_date),
                ("status_bar", "not in", ["checkout", "cancel"]),
            ]
        )

        current_date_check_out = self.search(
            [
                ("check_out", ">=", start_date),
                ("check_out", "<", end_date),
                ("status_bar", "=", "allot"),
            ]
        )

        # Bookings that need confirmation (draft orders)
        bookings_to_confirm = self.env['hotel.booking'].search([
            ('status_bar', '=', 'initial'),
        ])

        fetch_data.update(
            {
                "room_data": room_data,
                "check_in_booking": current_date_check_in.ids,
                "check_out_booking": current_date_check_out.ids,
                "current_date_check_in": len(current_date_check_in),
                "current_date_check_out": len(current_date_check_out),
                "bookings_to_confirm": bookings_to_confirm.ids,
            }
        )
        
        return fetch_data

    def get_booked_and_available_rooms(self, selected_date):
        """method will use to calculate booked and available rooms"""
        product = self.env["product.product"]
        booking = self.env["hotel.booking"]
        # total room that are available for booking
        room_type_product = product.search(
            [("is_room_type", "=", True), ("active", "=", True)]
        )
        not_available_booking = booking.search(
            [
                ("check_out", ">", selected_date.date()),
                ("check_in", "<=", datetime.combine(selected_date, dt.time.max)),
                ("status_bar", "not in", ["initial", "checkout"]),
            ]
        )
        booked_rooms = not_available_booking.booking_line_ids.mapped(
            "product_id"
        )  # getting rooms from booking
        # getting calculated available rooms
        available_rooms = room_type_product - booked_rooms
        return booked_rooms, available_rooms

    def get_count_of_booking(self, selected_date_data, today_date):
        """fetch the booking id & count"""
        product = self.env["product.product"]
        booking = self.env["hotel.booking"]
        date_eligible = True
        # case 1: In if condition we are checking that selected date is past date
        # case 2: if selected date is not past date then get check in/out booking
        selected_date = datetime.combine(selected_date_data, datetime.min.time())
        if selected_date_data < today_date:
            (
                date_eligible,
                current_date_check_in,
                current_date_check_out,
                booked_rooms,
                available_rooms,
            ) = [False, booking, booking, product, product]
        else:
            current_date_check_in = self.search(
                [
                    ("check_in", ">=", selected_date),
                    ("check_in", "<", selected_date + dt.timedelta(days=1)),
                    ("status_bar", "in", ["confirm", "initial", "allot"]),
                ]
            )
            current_date_check_out = self.search(
                [
                    ("check_out", ">=", selected_date),
                    ("check_out", "<", selected_date + dt.timedelta(days=1)),
                    ("status_bar", "=", "allot"),
                ]
            )

        # here we are getting booking that have checkout date after seletced date
        if date_eligible:
            booked_rooms, available_rooms = self.get_booked_and_available_rooms(
                selected_date
            )

        return {
            "current_month_check_in": len(current_date_check_in),
            "current_month_check_out": len(current_date_check_out),
            "check_in_booking": current_date_check_in.ids,
            "check_out_booking": current_date_check_out.ids,
            "booked_room_ids": booked_rooms.ids,
            "available_rooms": len(available_rooms),
            "available_rooms_name": available_rooms.read(
                ["display_name", "product_tmpl_id"]
            ),
        }

    def fetch_booking_count_for_dashboard(self, **kwarg):
        """fetching data onchange scale, possible values ['MONTH','YEAR','WEEK', 'DAY']"""

        selected_date = (
            str(kwarg["calendar_data"].get("day"))
            + "/"
            + str(kwarg["calendar_data"].get("month"))
            + "/"
            + str(kwarg["calendar_data"].get("year"))
        )
        today_date = fields.Date.today()
        return self.get_count_of_booking(
            datetime.strptime(selected_date, "%d/%m/%Y").date(), today_date
        )

    def current(self):
        if request and request.env.user.has_group("base.group_portal"):
            return self.filtered(lambda _: _.product_id.sudo().website_published)
        return self

    def action_view_order(self):
        order_id = 0
        result = self.env["ir.actions.act_window"]._for_xml_id(
            "sale.action_quotations_with_onboarding"
        )
        res = self.env.ref("sale.view_order_form", False)
        form_view = [(res and res.id or False, "form")]
        if "views" in result:
            result["views"] = form_view + [
                (state, view) for state, view in result["views"] if view != "form"
            ]
        else:
            result["views"] = form_view
        order_id = self.env["sale.order"].search([("id", "=", self.order_id.id)])
        result["res_id"] = order_id.id
        return result

    def sale_order_view(self):
        active_id = self.id
        domain = []
        context = {
            "default_booking_id": self.id,
            "default_partner_id": self.partner_id.id,
            "default_hotel_check_in": self.check_in,
            "default_hotel_check_out": self.check_out,
        }
        if self.sale_order_ids:
            view = "tree,form"
            domain = [("booking_id", "=", active_id)]
        else:
            view = "form,tree"
        return {
            "name": "Sale Order",
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": view,
            "domain": domain,
            "target": "current",
            "context": context,
        }

    def validate_guest(self):
        for rec in self:
            for line in rec.booking_line_ids:
                adult = 0
                child = 0
                for guest in line.guest_info_ids:
                    if guest.is_adult:
                        adult += 1
                    else:
                        child += 1
                if line.max_adult < adult:
                    raise ValidationError(
                        _("Max Adult limit is exceed of " + line.booking_sequence_id)
                    )
                if line.max_child < child:
                    raise ValidationError(
                        _("Max Child limit is exceed of " + line.booking_sequence_id)
                    )

    def action_confirm_booking(self):
        self.validate_guest()
        if not self.env.context.get("bypass_checkin_checkout", False):
            self._check_validity_check_in_check_out_booking()

        if self.status_bar == "initial":
            if self.booking_reference == 'via_agent' and self.commission_type == 'fixed' and not self.agent_commission_amount:
                raise ValidationError(_("Please specify the agent commission on agent info tab!"))
            if self.booking_reference == 'via_agent' and self.commission_type == 'percentage' and not self.agent_commission_percentage:
                raise ValidationError(_("Please specify the agent commission on agent info tab!"))
            if not self.booking_line_ids:
                raise ValidationError(_("Please add rooms for booking confirmation!"))
            if not all([line.guest_info_ids.ids for line in self.booking_line_ids]):
                raise ValidationError(_("Please fill the members details !!"))
            else:
                if self.booking_reference != "sale_order":
                    sale_order = self.env["sale.order"].create(
                        {
                            "state": "sale",
                            "hotel_check_in": self.check_in,
                            "booking_id": self.id,
                            "partner_id": self.partner_id.id,
                            "hotel_check_out": self.check_out,
                            "pricelist_id": (
                                self.pricelist_id.id if self.pricelist_id else False
                            ),
                            "hotel_id": self.hotel_id.id,
                            "booking_count":1,
                        }
                    )

                    for line in self.booking_line_ids:
                        sale_order_line = self.env["sale.order.line"].create(
                            {
                                "tax_id": line.tax_ids,
                                "order_id": sale_order.id,
                                "product_id": line.product_id.id,
                                "product_uom_qty" : self.booking_days,
                                "price_unit" : line.price,
                                "guest_info_ids": line.guest_info_ids,
                                "discount": line.discount,
                            }
                        )
                        line.sale_order_line_id = sale_order_line.id

                    self.order_id = sale_order
                self.status_bar = "confirm"
                self.manage_check_in_out_based_on_restime()
                template_id = self.env.ref(
                    "hotel_management_system.hotel_booking_confirm_id"
                )
                confirm_config = (
                    self.env["ir.config_parameter"]
                    .sudo()
                    .get_param("hotel_management_system.send_on_confirm")
                )

                if (
                    not self.env.context.get("bypass_checkin_checkout", False)
                    and confirm_config
                ):
                    template_id.send_mail(self.id, force_send=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "company_id" in vals:
                self = self.with_company(vals["company_id"])
            if vals.get("sequence_id", _("New")) == _("New"):
                seq_date = (
                    fields.Datetime.context_timestamp(
                        self, fields.Datetime.to_datetime(vals["check_in"])
                    )
                    if "check_in" in vals
                    else None
                )
                vals["sequence_id"] = self.env["ir.sequence"].next_by_code(
                    "hotel.booking", sequence_date=seq_date
                ) or _("New")

        return super().create(vals_list)

    def _valid_field_parameter(self, field, name):
        return name == "tracking" or super()._valid_field_parameter(field, name)

    @api.depends("check_out", "check_in")
    def _compute_booking_days(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                rec.booking_days = (rec.check_out.date() - rec.check_in.date()).days
            else:
                rec.booking_days = 0

    @api.depends("booking_line_ids.subtotal_price")
    def _compute_actual_amount(self):
        for booking in self:
            total_tax_amount = 0
            total_amount = 0
            for line in booking.booking_line_ids:
                total_tax_amount += line.taxed_price
                total_amount += line.subtotal_price
            booking.tax_amount = total_tax_amount - total_amount
            booking.amount_untaxed = total_amount
            booking.total_amount = total_tax_amount

    def invoice_line_create(self, order_lines, inv_data):
        for line in order_lines:
            vals = line._prepare_invoice_line(quantity=line.product_uom_qty)
            inv_data["invoice_line_ids"].append((0, 0, vals))
        return inv_data

    def create_invoice(self):
        inv_obj = self.env["account.move"].sudo()
        order_ids = self.order_id
        order_line = order_ids.mapped("order_line")
        data = self.invoice_line_create(order_line, self._prepare_invoice())
        data.update({"hotel_booking_id": self.id})
        invoice = inv_obj.create(data)
        self.invoice = invoice.id

    def create_agent_bill(self):
        """
        Creates Vendor Bill for Agent for managing agent commission
        """
        try:
            agent_bill_product = self.env.ref(
                "hotel_management_system.product_agent_bill"
            )
        except ValueError:
            raise ValidationError(
                _(
                    "Agent Bill product is missing. Please ensure it is created during module installation."
                )
            )

        if (not self.agent_commission_amount and not self.agent_commission_percentage): 
            return

        commission_amount = 0.0
        if self.commission_type == "fixed":
            commission_amount = self.agent_commission_amount
        elif self.commission_type == "percentage":
            total_sales_amount = sum(self.order_id.mapped("amount_total"))
            commission_amount = (
                total_sales_amount * self.agent_commission_percentage
            ) / 100

        inv_obj = self.env["account.move"].sudo()
        invoice_vals = {
            "move_type": "in_invoice",
            "partner_id": self.agent_id.id,
            "invoice_date": fields.Date.context_today(self),
            "ref": self.sequence_id,
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": agent_bill_product.id,
                        "name": agent_bill_product.name,
                        "quantity": 1,
                        "price_unit": commission_amount,
                        "account_id": agent_bill_product.property_account_expense_id.id
                        or agent_bill_product.categ_id.property_account_expense_categ_id.id,
                    },
                )
            ],
        }

        agent_invoice = inv_obj.create(invoice_vals)

        self.write({"agent_invoice_id": agent_invoice.id})

        return {
            "name": _("Agent Bill"),
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "view_mode": "form",
            "res_id": agent_invoice.id,
        }

    def create_housekeeping(self):
        housekeeping_model = self.env["hotel.housekeeping"]
        team_id = self.env["crm.team"].search([("name", "=", "Housekeeping")])
        for line_id in self.booking_line_ids:
            rec = housekeeping_model.create(
                {
                    "booking_line_id": line_id.id,
                    "state": "draft",
                    "room_id": line_id.product_id.id,
                    "responsible": self.order_id.user_id.id,
                    "team_id": team_id.id if team_id else False,
                }
            )
            line_id.housekeeping_id = rec.id

    def manage_alloted_services(self):
        is_done = all(
            [line.state in ["done", "cancel"] for line in self.hotel_service_lines]
        )
        if not is_done:
            not_done_ids = [line.id for line in self.hotel_service_lines if line.state not in ["done", "cancel"]]
            return {
                "type": "ir.actions.act_window",
                "name": "Unpaid Services",
                "res_model": "hotel.service.checkout.wizard",
                "view_mode": "form",
                "target": "new",
                "context": {
                    'default_service_ids': not_done_ids,
                    "default_booking_id": self.id,
                },
            }
        all_done_services = self.hotel_service_lines.filtered(
            lambda service: service.state == "done"
        )

        paid_services = all_done_services.filtered(
            lambda service: service.service_type == "paid"
        )
        free_services = all_done_services.filtered(
            lambda service: service.service_type == "free"
        )

        if paid_services and free_services:
            service_name = "Alloted Services"
        elif paid_services:
            service_name = "Paid Services"
        else:
            service_name = "Free Services"

        self.sale_order_ids.write(
            {
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "name": service_name,
                            "display_type": "line_section",
                            "product_id": False,
                            "product_qty": 0.0,
                            "product_uom": False,
                            "price_unit": 0.0,
                            "tax_id": False,
                        },
                    )
                ]
            }
        )

        for line in all_done_services:
            product = line.product_id
            if not product:
                product = self.env.ref("hotel_management_system.product_hotel_service")

            service_value = True if line.service_type == "free" else False
            self.sale_order_ids.write(
                {
                    "order_line": [
                        (
                            0,
                            0,
                            {
                                "product_id": product.id,
                                "name": line.service_id.name,
                                "is_free_service": service_value,
                                "price_unit": (
                                    line.amount if line.service_type == "paid" else 0
                                ),
                            },
                        )
                    ]
                }
            )

    def action_checkout(self):
        self.ensure_one()
        if self.status_bar != "allot":
            raise ValueError(
                _("Checkout can only be performed when the status is 'Room Allocated'.")
            )
        
        res = self.manage_alloted_services()
        if(res): return res

        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.auto_invoice_gen")
        ):
            self.create_invoice()

        configg = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.feedback_config")
        )

        if configg == "at_checkout":
            self.send_feedback_btn()

        if (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.auto_bill_gen")
            and self.via_agent
        ):
            self.create_agent_bill()

        hk_mode = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.housekeeping_config")
        )

        if hk_mode in ["at_checkout", "both"]:
            self.create_housekeeping()
        
        # if res: return res
        self.status_bar = "checkout"

        email_on_checkout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.send_on_checkout")
        )

        if email_on_checkout: self.send_checkout_email()
        return

    def action_show_house_keeping(self):
        housekeeping_id = self.booking_line_ids.mapped("housekeeping_id")
        view_mode = ""
        action_dict = {
            "name": "House Keeping Line",
            "type": "ir.actions.act_window",
            "res_model": "hotel.housekeeping",
            "view_mode": view_mode,
            "target": "current",
        }
        if self.housekeeping_count > 1:
            view_mode = "tree,form"
            action_dict.update(
                {"domain": [("id", "in", housekeeping_id.ids)], "view_mode": view_mode}
            )
        else:
            view_mode = "form"
            form_view = [
                (
                    self.env.ref(
                        "hotel_management_system.hotel_housekeeping_form_view"
                    ).id,
                    "form",
                )
            ]
            action_dict.update({"views": form_view, "res_id": housekeeping_id.id})
        return action_dict

    def action_show_agent_bill(self):
        return {
            "name": "Agent Bill",
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.agent_invoice_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def _prepare_invoice(self):
        """
        Prepare the dict of values to create the new invoice for a sales order. This method may be
        overridden to implement custom invoice generation (making sure to call super() to establish
        a clean extension chain).
        """
        hotel_obj = self
        hotel_obj.ensure_one()
        journal_id = self.env["account.journal"].search(
            [("type", "=", "sale")], limit=1
        )
        invoice_vals = {
            "ref": (
                hotel_obj.order_id.name or ""
                if hotel_obj.booking_reference == "sale_order"
                else hotel_obj.sequence_id
            ),
            "move_type": "out_invoice",
            "invoice_line_ids": [],
            "partner_id": hotel_obj.partner_id.id,
            "journal_id": journal_id.id,
            "currency_id": hotel_obj.currency_id.id,
            "fiscal_position_id": (
                hotel_obj.order_id.fiscal_position_id.id
                if hotel_obj.booking_reference == "sale_order"
                else False
            ),
            "company_id": (
                hotel_obj.order_id.company_id.id
                if hotel_obj.booking_reference == "sale_order"
                else self.env.company.id
            ),
            "invoice_user_id": (
                hotel_obj.order_id.user_id and hotel_obj.order_id.user_id.id
                if hotel_obj.booking_reference == "sale_order"
                else self._uid
            ),
        }
        return invoice_vals

    def _find_appropriate_mail_template(self):
        """Get the appropriate mail template for the current booking based on its state.

        :return: The correct mail template based on the current status
        """
        self.ensure_one()
        if self.status_bar == "confirm":
            mail_template = self.env.ref(
                "hotel_management_system.hotel_booking_confirm_id"
            )
        elif self.status_bar == "allot":
            mail_template = self.env.ref(
                "hotel_management_system.hotel_booking_confirm_id"
            )
        elif self.status_bar == "cancel":
            mail_template = self.env.ref(
                "hotel_management_system.hotel_booking_confirm_id"
            )
        else:
            mail_template = self.env.ref(
                "hotel_management_system.hotel_booking_send_on_email_id"
            )
        return mail_template

    def action_booking_send(self):
        lang = self.env.context.get("lang")

        ctx = {
            "default_model": "hotel.booking",
            "default_res_ids": self.ids,
            "default_composition_mode": "comment",
            "default_email_layout_xmlid": "mail.mail_notification_layout_with_responsible_signature",
        }

        if len(self) > 1:
            ctx["default_composition_mode"] = "mass_mail"
        else:
            ctx.update(
                {
                    "force_email": True,
                    "model_description": self.with_context(lang=lang).sequence_id,
                }
            )
            mail_template = self._find_appropriate_mail_template()
            if mail_template:
                ctx.update(
                    {
                        "default_template_id": mail_template.id,
                    }
                )
            if mail_template and mail_template.lang:
                lang = mail_template._render_lang(self.ids)[self.id]

        action = {
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "mail.compose.message",
            "views": [(False, "form")],
            "view_id": False,
            "target": "new",
            "context": ctx,
        }
        return action

    def manage_check_in_out_based_on_restime(self):
        if (
            self.order_id
            and self.order_id.website_id
            and self.order_id.website_id.checkout_hours
        ):
            checkout_hours = self.order_id.website_id.checkout_hours
        else:
            checkout_hours = (
                self.env["ir.config_parameter"]
                .sudo()
                .get_param("hotel_management_system.checkout_hours")
                or 12.00
            )
        checkout_time_format = "{0:02.0f}:{1:02.0f}".format(
            *divmod(float(checkout_hours) * 60, 60)
        )
        tz = pytz.timezone(self.env.context.get("tz") or "UTC")
        required_time = datetime.strptime(checkout_time_format, "%H:%M").time()

        if self.check_in:
            check_in_date = self.check_in.date()
            combine_time_check_in = tz.localize(
                datetime.combine(check_in_date, required_time)
            )
            self.check_in = combine_time_check_in.astimezone(pytz.utc).replace(
                tzinfo=None
            )

        if self.check_out:
            check_out_date = self.check_out.date()
            combine_time_check_out = tz.localize(
                datetime.combine(check_out_date, required_time)
            )
            self.check_out = combine_time_check_out.astimezone(pytz.utc).replace(
                tzinfo=None
            )

    def _rating_get_parent_field_name(self):
        return 'hotel_id'
    
    def unlink(self):
        """
        Throwing UserError when deleting a un-cancelled booking.
        """
        for booking in self:
            if booking.status_bar != "cancel":
                raise UserError(
                    _(
                        "You cannot delete a booking that is not 'Cancelled'. "
                        "Please Cancel the booking before deleting."
                    )
                )
        return super().unlink()

    @api.depends('pricelist_id', 'company_id')
    def _compute_currency_id(self):
        for booking in self:
            booking.currency_id = booking.pricelist_id.currency_id or booking.company_id.currency_id

class HotelBookingLine(models.Model):
    _name = "hotel.booking.line"
    _description = "Booking Line"
    _rec_name = "product_id"

    booking_sequence_id = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _("New"),
    )
    image_1920 = fields.Image(related="product_id.image_1920")
    product_id = fields.Many2one("product.product", string="Rooms")
    booking_id = fields.Many2one("hotel.booking", readonly=True, copy=False)
    guest_info_ids = fields.One2many(
        "guest.info", "booking_line_id", string="Members", required=True
    )
    price = fields.Float(string="Price Per Night", store=True)
    description = fields.Html("Description ", compute="_get_description", store=True)
    tax_ids = fields.Many2many("account.tax", string="Taxes")
    booking_days = fields.Integer(
        string="Days Book For", related="booking_id.booking_days", copy=False
    )
    subtotal_price = fields.Float(string="Subtotal", compute="_compute_amount")
    taxed_price = fields.Float(string="taxed amount", compute="_compute_amount")
    currency_id = fields.Many2one(related="booking_id.currency_id", string="Currency")
    status_bar = fields.Selection(related="booking_id.status_bar", copy=False)
    product_tmpl_id = fields.Many2one(
        "product.template", related="product_id.product_tmpl_id"
    )
    max_child = fields.Integer(related="product_tmpl_id.max_child", string="Max Child")
    max_adult = fields.Integer(related="product_tmpl_id.max_adult", string="Max Adult")
    sale_order_line_id = fields.Many2one("sale.order.line", string="Sale Order Line")
    housekeeping_id = fields.Many2one("hotel.housekeeping", string="HouseKeeping")
    check_in = fields.Datetime(related="booking_id.check_in")
    check_out = fields.Datetime(related="booking_id.check_out")
    hotel_service_lines = fields.One2many(
        "hotel.booking.service.line",
        "booking_line_id",
        string="Service Lines",
    )
    warning = fields.Text(string="Warning In Hotel Booking Line", compute="_compute_warning", store=True, readonly=False)

    # Discount Improvement
    discount = fields.Float(
        string="Discount (%)",
        readonly=False,
        digits='Discount')

    @api.depends('guest_info_ids', 'guest_info_ids.is_adult')
    def _compute_warning(self):
        for line in self:
            adult = sum(1 for guest in line.guest_info_ids if guest.is_adult)
            child = len(line.guest_info_ids) - adult
            if not line.guest_info_ids:
                line.warning = "Please fill the members details !!"
            elif line.max_adult < adult and line.max_child < child:
                line.warning = "No. of Adult Guests and Child Guests cannot be greater than Max Adult and Child count"
            elif line.max_adult < adult:
                line.warning = "No. of Adult Guests cannot be greater than Max Adult count"
            elif line.max_child < child:
                line.warning = "No. of Child Guests cannot be greater than Max Child count"
            else:
                line.warning = ""

    @api.onchange("subtotal_price")
    @api.depends(
        "product_id",
        "price",
        "tax_ids",
        "discount",
        "subtotal_price",
        "booking_id.check_out",
        "booking_id.check_in",
    )
    def _compute_amount(self):
        for line in self:
            discounted_price = line.price * (1 - (line.discount or 0.0) / 100.0)
            taxes = line.tax_ids.compute_all(
                discounted_price,
                line.booking_id.currency_id,
                1,
                product=line.product_id,
            )
            line.subtotal_price = taxes["total_excluded"] * line.booking_days
            line.taxed_price = taxes["total_included"] * line.booking_days

    @api.depends("product_id")
    def _get_description(self):
        for line in self:
            if line.product_id.description_sale:
                line.description = line.product_id.description_sale
            else:
                line.description = " "

    def write(self, vals):
        self.ensure_one()
        rec = super().write(vals)
        if self.sale_order_line_id:
            self.sale_order_line_id.write({
                                    "tax_id": self.tax_ids,
                                    "product_id": self.product_id.id,
                                    "product_uom_qty" : self.booking_days,
                                    "price_unit" : self.price,
                                    "guest_info_ids": self.guest_info_ids,
                                    "discount": self.discount
                                    })
        return rec

    def sale_order_view(self):
        active_id = self.id
        return {
            "name": "Sale Order",
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "tree",
            "domain": [("booking_line_id", "=", active_id)],
            "target": "new",
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "company_id" in vals:
                self = self.with_company(vals["company_id"])
            if vals.get("booking_sequence_id", _("New")) == _("New"):
                vals["booking_sequence_id"] = self.env["ir.sequence"].next_by_code(
                    "hotel.booking.line"
                ) or _("New")
        return super().create(vals_list)
    
    @api.onchange("product_id")
    def _onchange_product_id_set_taxes(self):
        for line in self:
            if line.product_id:
                line.tax_ids = line.product_id.taxes_id
            if line.product_id and line.booking_id.pricelist_id:
                line.price = line.booking_id.pricelist_id._get_product_price(
                    line.product_id, line.booking_days
                )
