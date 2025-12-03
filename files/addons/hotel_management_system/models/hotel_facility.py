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
###########################################################################
from odoo import fields, models


class HotelFacility(models.Model):
    """Facility In room

    Parameters
    ----------
    models : Model
    """

    _name = "hotel.facility"
    _description = "Hotel Facilities"

    name = fields.Char("Name")
    logo = fields.Binary("Logo")
    color = fields.Integer()
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.company.currency_id,
    )
    price = fields.Monetary(
        "Price", help="This price will be add in total amount as extra charge"
    )

    _sql_constraints = [
        ("name_uniq", "UNIQUE(name)", "Facility will unique always!!!"),
    ]
