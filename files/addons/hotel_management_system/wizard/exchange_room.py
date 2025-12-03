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
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging
_logger = logging.getLogger(__name__)

class ExchangeRoom(models.TransientModel):
    _name = "exchange.room"
    _description = "Exchange rooms if available"

    booking_line_id = fields.Many2one('hotel.booking.line', string='Reference No')
    price =  fields.Float(related = 'booking_line_id.price' , string="Current Price")
    available_room_ids = fields.Many2many('product.product')
    exchange_room=fields.Many2one('product.product', string='Exchange Room')
    exchange_price = fields.Float(related = "exchange_room.lst_price",string="Exchange Price")
    price_difference = fields.Float(compute='_compute_price_difference',store=True, string="Price Difference")
    warning = fields.Text(string="Warning In Exchange Rooms", compute="_compute_warning", store=True, readonly=False)
    
    @api.depends('exchange_room')
    def _compute_price_difference(self):
        for rec in self:
            if rec.exchange_room:
                booking_line = self.env['hotel.booking.line'].browse(self._context.get("active_ids"))
                rec.price_difference = booking_line.price - rec.exchange_room.lst_price

                adult = sum(1 for guest in rec.booking_line_id.guest_info_ids if guest.is_adult)
                child = len(rec.booking_line_id.guest_info_ids) - adult

                if adult > rec.exchange_room.max_adult or child > rec.exchange_room.max_child:
                    rec.warning = "The number of current guests exceeds the room's allowed limit."
                else:
                    rec.warning = ""
            
    @api.onchange('booking_line_id')
    def booking_line_compute(self):
        booking_line = self.env['hotel.booking.line'].browse(self._context.get("active_ids"))
        self.booking_line_id = booking_line
        self.available_room_ids = self._check_available_exchange_room(booking_line)

    def _check_available_exchange_room(self,booking_line):
        if self.booking_line_id:
            self.available_room_ids = False
            active_booking = booking_line.booking_id

            check_in = active_booking.check_in
            check_out = active_booking.check_out
            booking = self.env['hotel.booking'].search([])

            product_ids = self.env['product.product'].search([("product_tmpl_id.is_published", "=", True), ("product_tmpl_id.is_room_type", "=", True), ('hotel_id', '=', active_booking.hotel_id.id)])
            if booking:
                booked_booking_ids = booking.filter_booking_based_on_date(check_in, check_out)
                return product_ids - booked_booking_ids.mapped('booking_line_ids.product_id')

            # Now we want to show all type of available rooms at the time of exchange

            # eligible_products = self.env['product.product'].search(
            #     [("product_tmpl_id", "=", room_temp_id.id), ("product_tmpl_id.is_room_type", "=", True)])
            # if product_ids:
            #     final_available_products = eligible_products.filtered(
            #         lambda r: r if r.id not in product_ids else None)
            # else:
            #     final_available_products = eligible_products
            return product_ids

    def action_exchange_room(self):
        booking_line = self.env['hotel.booking.line'].browse(self._context.get("active_ids"))
        line = booking_line.sale_order_line_id

        if not (booking_line or line): return
        order = booking_line.sale_order_line_id.order_id

        if order:
            posted_invoice_count = len(order.invoice_ids.filtered(lambda i: i.state == 'posted'))

            if(posted_invoice_count):
                raise ValidationError(_('You cannot exchange a room if an invoice or delivery has been created for the related sale order.'))
            elif(self.exchange_room):
                booking_line.product_id = self.exchange_room.id
                order.state = "draft"
                line.unlink()
                sale_order_line = self.env['sale.order.line'].create({
                    'order_id': order.id,
                    'product_id': booking_line.product_id.id,
                    'tax_id': [(6, 0, booking_line.tax_ids.ids)],
                    'price_unit': booking_line.subtotal_price,
                    'guest_info_ids': [(6, 0, booking_line.guest_info_ids.ids)]
                })
                booking_line.sale_order_line_id = sale_order_line.id
                order.state = "sale"
            templ_id= self.env.ref('hotel_management_system.hotel_booking_exchange_id')
            templ_id.send_mail(booking_line.booking_id.id,force_send=True)     
            return True
        else:
            return self.env['wk.wizard.message'].genrated_message("Exchange is not possible", name='Message')

class AvailableProduct(models.TransientModel):
    _name = "available.product"
    _description = "Available Rooms"

    name = fields.Char("Room Name")
    room_id = fields.Integer("Room Id", store=True)
    exchange_id = fields.Many2one("exchange.room")
    template_attribute_value_ids = fields.Many2many('product.template.attribute.value', string="Attribute Values")
