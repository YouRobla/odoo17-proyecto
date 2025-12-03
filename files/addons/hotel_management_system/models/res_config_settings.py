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
import pytz
from datetime import datetime
from odoo import fields, models, api
from odoo.exceptions import UserError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    def _default_housekeeping_id(self):
        return self.env["crm.team"].search([("name", "=", "Housekeeping")], limit=1)

    website_homepage_product_ids = fields.Many2many(
        "product.template",
        related="website_id.website_homepage_product_ids",
        readonly=False,
    )
    checkout_hours = fields.Float(
        string="Checkout Hours", related="website_id.checkout_hours", readonly=False
    )
    hotel_product_variant = fields.Many2many(
        "product.template",
        string="Trending Products",
        related="website_id.hotel_product_variant",
        readonly=False,
    )
    cron_id = fields.Many2one(
        "ir.cron", related="website_id.cron_id", readonly=False, store=True
    )
    interval_number = fields.Integer(
        related="website_id.interval_number", readonly=False
    )
    interval_type = fields.Selection(
        string="Interval Type", related="website_id.interval_type", readonly=False)
    max_trending_limit = fields.Integer(
        related="website_id.max_trending_limit", default=8, readonly=False
    )
    auto_invoice_gen = fields.Boolean(
        string="Automatic Invoice Generation",
        config_parameter="hotel_management_system.auto_invoice_gen",
    )
    auto_room_selection = fields.Boolean(
        string="Auto Room No Selection",
        config_parameter="hotel_management_system.auto_room_selection",
        help="If enabled then NO Room no. selection will be available on Website. Room no. will be selected in the automatically on the basis of availability.",
    )
    auto_bill_gen = fields.Boolean(
        string="Automatic Bill Generation",
        config_parameter="hotel_management_system.auto_bill_gen",
    )
    housekeeping_config = fields.Selection(
        [
            ("daily", "Daily"),
            ("at_checkout", "At Checkout"),
            ("both", "Both"),
            ("none", "None"),
        ],
        default="at_checkout",
        string="Housekeeping Configuration ",
        config_parameter="hotel_management_system.housekeeping_config",
    )

    team_id = fields.Many2one(
        "crm.team",
        string="HouseKeeping Team",
        default=_default_housekeeping_id,
    )

    feedback_config = fields.Selection(
        [
            ("manual", "Manual"),
            ("at_checkout", "At Checkout"),
        ],
        string="Feedback Configuration ",
        config_parameter="hotel_management_system.feedback_config",
    )

    send_on_confirm = fields.Boolean(
        "Send Email On Booking Confirmation", config_parameter="hotel_management_system.send_on_confirm"
    )

    send_on_allot = fields.Boolean(
        "Send Email On Room Allotment", config_parameter="hotel_management_system.send_on_allot"
    )

    send_on_cancel = fields.Boolean(
        "Send Email On Book Cancellation", config_parameter="hotel_management_system.send_on_cancel"
    )

    send_on_checkout = fields.Boolean(
        "Send Email On Checkout", config_parameter="hotel_management_system.send_on_checkout"
    )

    auto_confirm_booking = fields.Boolean("Auto Confirm Booking", help="If enabled, then the booking associated to the sale order will be confirmed automatically after the full payment.",
                                          config_parameter="hotel_management_system.auto_confirm_booking")

    @api.onchange("interval_number", "interval_type")
    def _compute_interval_type(self):
        if self.interval_type and self.interval_number:
            self.cron_id.interval_type = self.interval_type
            self.cron_id.interval_number = self.interval_number

    @api.onchange("cron_id")
    def _compute_interval_number(self):
        self.interval_number = self.cron_id.interval_number

    @api.onchange("checkout_hours")
    def onchange_checkout_hours(self):
        if not self.checkout_hours:
            self.checkout_hours = 12.00
        booking_ids = self.env["hotel.booking"].search(
            [("status_bar", "in", ["initial"])]
        )
        try:
            checkout_time_format = "{0:02.0f}:{1:02.0f}".format(
                *divmod(self.checkout_hours * 60, 60)
            )
            tz = pytz.timezone(self.env.context.get("tz") or "UTC")
            required_time = datetime.strptime(
                checkout_time_format, "%H:%M").time()
            for booking in booking_ids:
                if booking.check_in:
                    check_in_date = booking.check_in.date()
                    combine_time_check_in = tz.localize(
                        datetime.combine(check_in_date, required_time)
                    )
                    check_in = combine_time_check_in.astimezone(pytz.utc).replace(
                        tzinfo=None
                    )
                if booking.check_out:
                    check_out_date = booking.check_out.date()
                    combine_time_check_out = tz.localize(
                        datetime.combine(check_out_date, required_time)
                    )
                    check_out = combine_time_check_out.astimezone(pytz.utc).replace(
                        tzinfo=None
                    )
                booking.write({"check_in": check_in, "check_out": check_out})
        except Exception as e:
            raise UserError(e)

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        res.update(
            housekeeping_config=self.env["ir.config_parameter"].sudo().get_param(
                "hotel_management_system.housekeeping_config")
        )

        # Advance Payment
        IrDefault = self.env['ir.default'].sudo()
        account_receivable_id = IrDefault._get(
            'res.config.settings', 'account_receivable')
        res.update({
            'account_receivable': account_receivable_id,
        })

        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        self.env["ir.config_parameter"].sudo().set_param(
            "hotel_management_system.housekeeping_config", self.housekeeping_config or "at_checkout"
        )

        # Advance Payment
        IrDefault = self.env['ir.default'].sudo()
        for config in self:
            IrDefault.set('res.config.settings', 'account_receivable',
                          config.account_receivable.id if config.account_receivable else False)

    # Advance Payment configs
    account_receivable = fields.Many2one(
        comodel_name='account.account', string="Receivable Account", domain="[('deprecated', '=', False)]", readonly=False)
