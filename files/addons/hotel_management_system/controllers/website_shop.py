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
from datetime import datetime
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.variant import WebsiteSaleVariantController


class WebsiteShopInherit(WebsiteSale):
    @http.route()
    def shop_payment(self, **post):
        res = super(WebsiteShopInherit, self).shop_payment(**post)
        sale_order = request.website.sale_get_order()
        order_line = sale_order.order_line
        for line in order_line:
            if line.product_id.product_tmpl_id.is_room_type:
                if not line.guest_info_ids:
                    return request.redirect("/guest/page")
        return res

    @http.route()
    def checkout(self, **post):
        sale_order = request.website.sale_get_order()
        room_type_product = (sale_order.order_line).filtered(
            lambda r: r if r.product_id.product_tmpl_id.is_room_type else None
        )
        if room_type_product and room_type_product.filtered(
            lambda r: not r.guest_info_ids
        ):
            return request.redirect("/guest/page")
        return super(WebsiteShopInherit, self).checkout(**post)

    @http.route()
    def shop(
        self,
        page=0,
        category=None,
        min_price=0.0,
        max_price=0.0,
        search="",
        ppg=False,
        **post,
    ):
        request.session["check_in"] = post.get("check_in", False)
        request.session["check_out"] = post.get("check_out", False)
        request.session["members"] = post.get("members", False)
        return super(WebsiteShopInherit, self).shop(
            page=page,
            category=category,
            min_price=min_price,
            max_price=max_price,
            search=search,
            ppg=ppg,
            **post,
        )

    def _shop_get_query_url_kwargs(self, category, search, min_price, max_price, order=None, tags=None, attribute_value=None, **post):
        vals = super(WebsiteShopInherit, self)._shop_get_query_url_kwargs(
            category, search, min_price, max_price, order=None, tags=None, attribute_value=None, **post)
        if post.get("hotel_id"):
            vals.update({'hotel_id': post.get("hotel_id")})

        return vals

    @http.route()
    def cart(self, access_token=None, revive="", **post):
        sale_order = request.website.sale_get_order()
        if (sale_order.order_line.product_id).filtered(
            "product_tmpl_id.is_room_type"
        ) and not sale_order.hotel_check_in:
            sale_order.is_room_type = True
        return super(WebsiteShopInherit, self).cart(
            access_token=access_token, revive=revive, **post
        )

    @http.route()
    def product(self, product, category="", search="", **kwargs):
        res = super(WebsiteShopInherit, self).product(
            product, category=category, search=search, **kwargs
        )
        check_in = request.session.get("check_in", False)
        check_out = request.session.get("check_out", False)
        if product.sudo().is_room_type:
            product.sudo().count += 1
        if check_in and check_out:
            res.qcontext.update(
                {
                    "check_in_cart": datetime.strptime(check_in, "%m/%d/%Y"),
                    "check_out_cart": datetime.strptime(check_out, "%m/%d/%Y"),
                }
            )
        return res

    @http.route("/get/website/room", type="http", website=True, auth="public", sitemap=False)
    def get_room(self):
        website_id = request.website
        product_ids = website_id.sudo().website_homepage_product_ids.filtered(
            lambda x: x.is_published
        )
        pricelist = website_id.sudo()._get_current_pricelist()
        room_template = request.render(
            "hotel_management_system.home_rooms",
            {"product_ids": product_ids, "website": website_id, "pricelist": pricelist},
        )
        return room_template

    @http.route("/get/trending/room", type="http", website=True, auth="public", sitemap=False)
    def get_trending_room(self):
        website_id = request.website
        product_ids = website_id.sudo().hotel_product_variant
        pt = (
            request.env["product.template"]
            .sudo()
            .search(
                [
                    ("count", ">", 0),
                    ("is_room_type", "=", True),
                    ("is_published", "=", True),
                ],
                limit=website_id.max_trending_limit,
                order="count DESC",
            )
        )
        if len(pt) < website_id.max_trending_limit:
            temp = product_ids.sudo().search(
                [
                    ("id", "not in", pt.ids),
                    ("id", "in", product_ids.ids),
                    ("is_published", "=", True),
                ],
                limit=website_id.max_trending_limit - len(pt),
            )
        product_template_ids = pt
        if len(pt) < website_id.max_trending_limit and len(product_ids):
            product_template_ids = pt + temp
        else:
            product_template_ids
        pricelist = website_id.sudo()._get_current_pricelist()
        room_template = request.render(
            "hotel_management_system.hotel_trending_products_test",
            {
                "product_ids": product_template_ids,
                "website": website_id,
                "pricelist": pricelist,
            },
        )
        return room_template

    @http.route(["/empty/cart"], type="json", auth="public", website=True, sitemap=False)
    def empty_cart(self, **kw):
        sale_order = request.website.sudo().sale_get_order()
        sale_order.order_line = False

    @http.route(['/available/qty/details'], type='json', auth="public", website=True, sitemap=False)
    def cal_room_availability(self, requirement_qty='', product_template_id='', product_id='', hotel_id='', check_in='', check_out='', availabilty_check='', order_des=''):
        if requirement_qty and product_template_id:
            sale_order = request.website.sale_get_order(force_create=True)
            check_in_val = datetime.strptime(check_in, '%Y-%m-%d')
            check_out_val = datetime.strptime(check_out, '%Y-%m-%d')

            if sale_order.order_line:
                hotel_id = int(hotel_id or 0)
                new_hotel = request.env['hotel.hotels'].browse(hotel_id)

                if (sale_order.hotel_id.id and sale_order.hotel_id.id != hotel_id) and (
                    (sale_order.hotel_check_in and sale_order.hotel_check_out) and
                    (sale_order.hotel_check_in.date() != check_in_val.date()
                     or sale_order.hotel_check_out.date() != check_out_val.date())
                ):
                    return {'result': 'unmatched', 'both': True, 'msg': f"The check-In check-Out duration({check_in_val.date()} - {check_out_val.date()}) and Hotel({new_hotel.name}) does not match the exisitng order check-In check-Out duration({sale_order.hotel_check_in.strftime('%Y-%m-%d')} - {sale_order.hotel_check_out.strftime('%Y-%m-%d')}) and Hotel({sale_order.hotel_id.name})"}

                if sale_order.hotel_id.id and sale_order.hotel_id.id != hotel_id:
                    return {'result': 'unmatched', 'both': False, 'msg': _(f"There's already a room booking in cart for Hotel({sale_order.hotel_id.name}), you're trying to add a room which belongs to the Hotel({new_hotel.name})")}

                if (sale_order.hotel_check_in and sale_order.hotel_check_out) and (
                    sale_order.hotel_check_in.date() != check_in_val.date() or
                    sale_order.hotel_check_out.date() != check_out_val.date()
                ):
                    return {'result': 'unmatched', 'both': False, 'msg': _(f"The check-In check-Out duration({check_in_val.date()} - {check_out_val.date()}) for which you're trying to add does not match to the existing cart order check-In check-Out duration({sale_order.hotel_check_in.strftime('%Y-%m-%d')} - {sale_order.hotel_check_out.strftime('%Y-%m-%d')})")}
            else:
                sale_order.write(
                    {'hotel_check_in': check_in_val, 'hotel_check_out': check_out_val})

            product_template = request.env['product.template'].sudo().browse(
                int(product_template_id))
            total_room = product_template.product_variant_ids

            total_booking = request.env['hotel.booking'].sudo().search(
                [('status_bar', 'not in', ['initial', 'checkout'])])
            website_id = request.website
            pricelist = website_id.sudo()._get_current_pricelist()
            added_cart_room = 0

            sale_order.write({'hotel_id': int(hotel_id or 0)})

            for room in total_room:
                not_available = False
                if room.id not in (sale_order.mapped('order_line.product_id')).ids:
                    for booking in total_booking:
                        if room.id in (booking.mapped('booking_line_ids.product_id')).ids:
                            if booking.filter_booking_based_on_date(check_in_val, check_out_val):
                                not_available = True
                                break
                            else:

                                added_cart_room += 1
                                room_id = room
                                qty = (check_out_val.date() -
                                       check_in_val.date()).days or 1
                                price_unit = sale_order.pricelist_id._get_product_price(
                                    room_id, qty)
                                if availabilty_check == '0':
                                    if order_des:
                                        name = room_id.name + \
                                            '('+check_in+' ' + check_out + \
                                            ')' + f'\n {order_des}'
                                    else:
                                        name = room_id.name + \
                                            '('+check_in+' ' + check_out+')'
                                    request.env['sale.order.line'].sudo().create({
                                        'name': name,
                                        'product_id': room_id.id,
                                        'product_uom_qty': qty,
                                        'product_uom': room_id.uom_id.id,
                                        'price_unit': price_unit,
                                        'order_id': sale_order.id,
                                    })
                                break

                    # if room not in booking list
                    if room.id not in (sale_order.mapped('order_line.product_id')).ids and not_available is False:
                        added_cart_room += 1
                        room_id = room
                        qty = (check_out_val.date() -
                               check_in_val.date()).days or 1
                        price_unit = sale_order.sudo().pricelist_id._get_product_price(room_id, qty)
                        if availabilty_check == '0':
                            if order_des:
                                name = room_id.name + f'\n {order_des}'
                            else:
                                name = room_id.name
                            request.env['sale.order.line'].sudo().create({
                                'name': name,
                                'product_id': room_id.id,
                                'product_uom_qty': qty,
                                'product_uom': room_id.uom_id.id,
                                'price_unit': price_unit,
                                'order_id': sale_order.id,
                            })
                    if added_cart_room == int(requirement_qty) and availabilty_check == '0':
                        return {'result': 'done', }

            if availabilty_check == '1' and added_cart_room:
                return {'result': 'done', 'tot_available_room': added_cart_room}

            if added_cart_room < int(requirement_qty):
                msg = ' '
                if added_cart_room:
                    msg = f'{added_cart_room} rooms have been added to the cart, remaining rooms are not available currently...'
                return {'result': 'fail', 'msg': msg}

    @http.route(['/shop/cart/update_json'], type='json', auth="public", methods=['POST'], website=True, sitemap=False)
    def cart_update_json(self, product_id, line_id=None, add_qty=None, set_qty=None, display=True, product_custom_attribute_values=None, no_variant_attribute_value_ids=None, **kwargs):
        res = super(WebsiteShopInherit, self).cart_update_json(product_id, line_id, add_qty, set_qty,
                                                               display, product_custom_attribute_values, no_variant_attribute_value_ids, **kwargs)
        order = request.website.sale_get_order()
        if not order.cart_quantity:
            order.hotel_id = None
        return res


class GuestInfoController(http.Controller):
    @http.route(["/guest/info"], type="json", auth="public", website=True, sitemap=False)
    def discount(self, guest_detail="", **kw):
        for key, val in guest_detail.items():
            order_line_id = request.env["sale.order.line"].sudo().browse(
                int(key))
            order_line_id.guest_info_ids = False
            guest_info_data = [(0, 0, data) for data in val]
            order_line_id.write({"guest_info_ids": guest_info_data})


class GuestPageController(http.Controller):
    @http.route("/guest/page", type="http", auth="public", website=True, csrf=False, sitemap=False)
    def guest_info_page(self, **kw):
        sale_order = request.website.sudo().sale_get_order()
        if sale_order and sale_order.order_line.product_id.filtered(
            "product_tmpl_id.is_room_type"
        ):
            return request.render("hotel_management_system.guest_info_page")
        else:
            return request.redirect("/shop/cart")


class RoomPriceList(WebsiteSaleVariantController):

    @http.route()
    def get_combination_info_website(
        self,
        product_template_id,
        product_id,
        combination,
        add_qty,
        parent_combination=None,
        **kwargs,
    ):
        if product_template_id:
            product_template = (
                request.env["product.template"].sudo().browse(
                    product_template_id)
            )
            if product_template.is_room_type and kwargs.get("days_count"):
                add_qty = kwargs.get("days_count")

        res = super(RoomPriceList, self).get_combination_info_website(
            product_template_id=product_template_id,
            product_id=product_id,
            combination=combination,
            add_qty=add_qty,
            parent_combination=parent_combination,
            **kwargs,
        )
        return res
