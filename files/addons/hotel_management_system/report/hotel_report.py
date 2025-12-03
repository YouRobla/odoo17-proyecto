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
from odoo import fields, models, api


class HotelReport(models.Model):
    _name = "hotel.report"
    _description = "Hotel Analysis Report"
    _auto = False
    _rec_name = "check_in"
    _order = "check_in desc"

    sale_order_ids = fields.One2many("sale.order", "booking_id", readonly=True)
    booking_generate = fields.Boolean("Booking Already Available", readonly=True)
    order_id = fields.Many2one("sale.order", "Sale Order", readonly=True)
    booking_line_ids = fields.One2many(
        "hotel.booking.line", "booking_id", string="Booking Line", readonly=True
    )
    partner_id = fields.Many2one("res.partner", "Guest Name", readonly=True)
    check_in = fields.Datetime("ARRIVAL", readonly=True)
    check_out = fields.Datetime("DEPARTURE", readonly=True)
    status_bar = fields.Selection(
        [
            ("initial", "Draft"),
            ("confirm", "Confirm"),
            ("allot", "Room Allocated"),
            ("cancel", "Cancel"),
        ],
        readonly=True,
    )
    booking_reference = fields.Selection(
        [
            ("sale_order", "Sale order"),
            ("manual", "Manual"),
        ],
        readonly=True,
    )
    pricelist_id = fields.Many2one(
        "product.pricelist", string="Pricelist", readonly=True
    )
    currency_id = fields.Many2one(
        string="Currency",
        comodel_name='res.currency',
        compute='_compute_currency_id',
        store=True,
        precompute=True,
    )

    # currency_id = fields.Many2one(related="pricelist_id.currency_id", readonly=True)
    amount_untaxed = fields.Monetary("Amount Untaxed", readonly=True)
    total_amount = fields.Monetary("Total amount", readonly=True)
    booking_discount = fields.Monetary("Discount", readonly=True)
    tax_amount = fields.Monetary(string="Tax Amount", readonly=True)

    @api.depends('pricelist_id')
    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.pricelist_id.currency_id or self.env.company.currency_id
