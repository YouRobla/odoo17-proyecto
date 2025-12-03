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
from odoo.addons.sale.controllers import portal as sale_portal
from odoo.addons.website_sale.controllers.main import WebsiteSale, PaymentPortal as payment_website_sale

from odoo.exceptions import AccessError, ValidationError, MissingError
from odoo.fields import Command
from odoo.tools import float_compare
from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.controllers.portal import PaymentPortal
from odoo.addons.website_sale.controllers.delivery import WebsiteSaleDelivery

import logging
_logger = logging.getLogger(__name__)


class HotelSnippet(http.Controller):
    """
    Dedicated Controller for Website Multi-Hotel Snippets
    """
    def get_hotels(self):
        return request.env['hotel.hotels'].sudo().search([
            ("is_published", "=", True),
            "|",
            ('website_id', '=', request.website.id),
            ('website_id', '=', False)
        ])

    @http.route(["/wk/get_hotels"], type="json", auth="public", website=True, sitemap= False)
    def get_snippet_hotels(self):
        hotels = self.get_hotels()
        hotel_data = hotels.read(['id', 'name', 'address', 'image'])

        for hotel_dict, hotel in zip(hotel_data, hotels):
            hotel_dict['number_of_rooms'] = sum(
                room.product_variant_count for room in hotel.room_ids
            )

        return hotel_data

    @http.route('/hotels', type='http', auth="public", website=True, fields=[], sitemap= True)
    def hotel_list(self):
        hotels = self.get_hotels()
        return request.render('hotel_management_system.hotel_template', {'hotels': hotels})

    @http.route(['/hotel/<model("hotel.hotels"):hotel>'], type='http', auth="public", website=True, sitemap= True)
    def hotel_detail(self, hotel, **kwargs):
        return request.render('hotel_management_system.hotel_detail_template', {
            'hotel': hotel
        })


class WebsiteSale(WebsiteSale):
    """
    Overriding for Filtering Rooms on the basis of Hotels
    """

    def _get_search_options(
        self,
        category=None,
        attrib_values=None,
        tags=None,
        min_price=0.0,
        max_price=0.0,
        conversion_rate=1,
        **post
    ):
        options = super()._get_search_options(
            category=category,
            attrib_values=attrib_values,
            tags=tags,
            min_price=min_price,
            max_price=max_price,
            conversion_rate=conversion_rate,
            **post
        )
        if (post.get("hotel_id")):
            options.update({"hotel_id": int(post.get("hotel_id"))})
        return options
    
    # Advance Payment Integration
    @http.route('/order/advance_payment/modal_content', type='json', auth='public', website=True, sitemap= False)
    def my_orders_reorder_modal_content(self, **post):
        render_values = {}
        order_sudo = request.website.sale_get_order()
        amount = post.get('amount', order_sudo.balance_amount)
        render_values['sale_order'] = order_sudo
        render_values['custom_link'] = f'''/payment/pay?reference={order_sudo.name}&amount={amount}&access_token={payment_utils.generate_access_token(
            order_sudo.partner_id.id, amount, order_sudo.currency_id.id
        )}&order_id={order_sudo.id}'''

        return request.env['ir.ui.view']._render_template(
            "hotel_management_system.aditional_payment_modal_content", render_values
        )
    
    @http.route('/order/advance_payment/check_hotel_advance_config', type='json', auth='public', website=True, sitemap= False)
    def advance_payment(self, **post):
        sale_order = request.website.sale_get_order()
        need_to_show = False
        minimum_amount = 0.0
        if sale_order.hotel_id:
            if sale_order.hotel_id.required_advance_payment:
                need_to_show = True
            if sale_order.hotel_id.advance_payment_type == 'percentage':
                if sale_order.hotel_id.advance_payment_percentage:
                    minimum_amount = sale_order.amount_total * sale_order.hotel_id.advance_payment_percentage / 100
            elif sale_order.hotel_id.advance_payment_type == 'fixed':
                if sale_order.hotel_id.advance_payment_value:
                    minimum_amount = sale_order.hotel_id.advance_payment_value
            else:
                minimum_amount = 0.0
            
        return {'need_to_show': need_to_show, 'adv_payment_len': len(sale_order.payment_ids), 'minimum_amount': minimum_amount, 'currency': sale_order.currency_id.name}


class BookingFeedbackController(sale_portal.CustomerPortal):

    @http.route('/remark/request', type='http', auth='public',csrf=False,website=True, sitemap= False)
    def remark(self,**kw):
        ratingObj = request.env['rating.rating'].sudo()
        if(kw.get('booking_id')):
            booking =  request.env['hotel.booking'].browse(int(kw.get('booking_id')))
            partner = booking.partner_id.id
            rating_search = ratingObj.search([('rated_partner_id','=',partner),('res_id','=',int(kw.get('booking_id'))),('res_model_id','=',request.env['ir.model']._get('hotel.booking').id)])
            
            if kw.get('feedback_count',False) and kw.get('booking_id') and not rating_search:
                ratingObj.create({
                    'res_id': int(kw.get('booking_id')),
                    'res_model_id': request.env['ir.model']._get('hotel.booking').id,
                    'feedback': kw.get('requestMessage', ''),
                    'rating': int(kw.get('feedback_count')),
                    'rated_partner_id':booking.partner_id.id,
                    'consumed': True,
                })
        return request.render("hotel_management_system.feedback_thank_you",{})    

    @http.route('/feedback/<int:booking_id>/', type='http',website=True,  auth="public", sitemap= False)
    def submit_feedback(self, booking_id=None, access_token=None, **kwargs):
        try:
            booking = self._document_check_access("hotel.booking",booking_id,access_token)
        except (AccessError, MissingError):
            return request.not_found()
        
        ratingObj = request.env['rating.rating'].sudo()
        partner = booking.partner_id.id
        rating_search = ratingObj.search([('rated_partner_id','=',partner),('res_id','=',int(booking.id)),('res_model_id','=',request.env['ir.model']._get('hotel.booking').id)])
        if rating_search:
            return request.render("hotel_management_system.feedback_already_accepted",{})  
        return request.render("hotel_management_system.remark_page",{'booking':booking})

class PaymentPortalAdvancePayment(PaymentPortal):

    def _create_transaction(self, *args, provider_reference=None, **kwargs):
        tx_sudo = super()._create_transaction(*args, provider_reference=provider_reference, **kwargs)
        if kwargs.get('advance_payment_order_id', False):
            tx_sudo.write({
                "sale_order_ids": [int(kwargs.get('advance_payment_order_id'))]
            })

        return tx_sudo

    @staticmethod
    def _validate_transaction_kwargs(kwargs, additional_allowed_keys=()):
        whitelist = {
            'provider_id',
            'payment_method_id',
            'token_id',
            'amount',
            'flow',
            'tokenization_requested',
            'landing_route',
            'is_validation',
            'csrf_token',
        }
        whitelist.update(additional_allowed_keys)
        rejected_keys = set(kwargs.keys()) - whitelist
        if "advance_payment_order_id" in rejected_keys:
            rejected_keys.remove("advance_payment_order_id")

        if rejected_keys:
            raise ValidationError(
                _("The following kwargs are not whitelisted: %s", ', '.join(rejected_keys))
            )
        

# Advance Payment Integration
class AdvancePaymentDelivery(WebsiteSaleDelivery):

    def _order_summary_values(self, order, **kwargs):
        Monetary = request.env['ir.qweb.field.monetary']
        currency = order.currency_id
        values = super()._order_summary_values(order, **kwargs)
        values.update({
            'amount_total': Monetary.value_to_html(
                order.balance_amount, {'display_currency': currency}
            ),            
        })

        return values


class PaymentPortal(payment_website_sale):
    @http.route()
    def shop_payment_transaction(self, order_id, access_token, **kwargs):
        if kwargs.get("advance_payment_order_id"):
            return super().shop_payment_transaction(order_id, access_token, **kwargs)

        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token)
        except MissingError:
            raise
        except AccessError as e:
            raise ValidationError(_("The access token is invalid.")) from e

        if order_sudo.state == "cancel":
            raise ValidationError(_("The order has been cancelled."))

        order_sudo._check_cart_is_ready_to_be_paid()
        self._validate_transaction_kwargs(kwargs)
        kwargs.update({
            'partner_id': order_sudo.partner_invoice_id.id,
            'currency_id': order_sudo.currency_id.id,
            'sale_order_id': order_id,
        })
        if not kwargs.get('amount'):
            kwargs['amount'] = order_sudo.balance_amount

        if float_compare(kwargs['amount'], order_sudo.balance_amount, precision_rounding=order_sudo.currency_id.rounding):
            raise ValidationError(_("The cart has been updated. Please refresh the page."))

        tx_sudo = self._create_transaction(
            custom_create_values={'sale_order_ids': [Command.set([order_id])]}, **kwargs,
        )
        request.session['__website_sale_last_tx_id'] = tx_sudo.id
        self._validate_transaction_for_order(tx_sudo, order_sudo)
        return tx_sudo._get_processing_values()
