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
from odoo import fields, models, api
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class GuestInfo(models.Model):
    """Module to manage Guest Information

    Parameters
    ----------
    models : importing Model
    """

    _name = "guest.info"
    _description = "Guest Information"

    name = fields.Char("Name", required=True)
    sale_order_line_id = fields.Many2one("sale.order.line")
    booking_line_id = fields.Many2one("hotel.booking.line")
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("other", "Other")],
        default="male",
        required=True,
    )
    age = fields.Integer("Age", required=True)
    is_adult = fields.Boolean(
        string="Is Adult", compute="_compute_is_Adult", default=False
    )

    @api.constrains('age')
    def _check_age(self):
        for record in self:
            if record.age <= 0:
                raise ValidationError("Age should be greater than 0")

    @api.depends("age")
    def _compute_is_Adult(self):
        for rec in self:
            if rec.age < 0:
                raise ValidationError("Age should not be negative")
            rec.is_adult = rec.age >= 18