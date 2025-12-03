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
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from odoo.addons.base.models.res_partner import _tz_get
from odoo.http import request
from odoo.osv import expression
from odoo.tools.float_utils import float_round
from odoo.addons.rating.models import rating_data


class HotelHotels(models.Model):
    """
    Multi-Hotel model
    """

    _name = "hotel.hotels"
    _inherit = ['rating.parent.mixin', 'mail.thread', 'mail.activity.mixin']
    _description = "Multi-Hotels"
    _mail_post_access = 'read'

    name = fields.Char("Name", required=True)
    partner_id = fields.Many2one(
        "res.partner", string="Partner", required=True)
    address = fields.Char(
        string="Address", related="partner_id.contact_address", store=True
    )
    tagline = fields.Char("TagLine")
    image = fields.Image("Hotel Logo")
    banner = fields.Image("Hotel Banner")
    policies = fields.Text("Policies")
    hotel_type_id = fields.Many2one("hotel.type", string="Hotel Type")
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company.id, required=True
    )
    website_id = fields.Many2one(
        "website", string="Website", ondelete="cascade")
    currency_id = fields.Many2one(
        string="Currency", related="company_id.currency_id")
    default_timezone = fields.Selection(
        _tz_get, string="Timezone", default=lambda self: self.env.user.tz or "UTC"
    )
    price_list_id = fields.Many2one("product.pricelist", string="Price List")
    room_ids = fields.One2many(
        "product.template",
        "hotel_id",
        string="Rooms",
        domain=[("is_room_type", "=", True), ("active", "=", True)],
    )
    description = fields.Text(
        "About", help="Provide detailed information about the hotel."
    )
    is_published = fields.Boolean(
        string="Published",
        help="Whether the hotel is visible on the website or not",
    )
    active = fields.Boolean(default=True)

    hotel_image_ids = fields.One2many(
        string="Extra Product Media",
        comodel_name='product.image',
        inverse_name='hotel_id',
        copy=False,
    )

    # -=-=-=-=-=-=-=-=-=- Advance Payment -=-=-=-=-=-=-=-=-=-
    required_advance_payment = fields.Boolean(
        string="Advance Payment Required",
        help="Whether the hotel requires advance payment or not",
    )
    advance_payment_type = fields.Selection(
        [("percentage", "Percentage"), ("fixed", "Fixed")],
        string="Advance Payment Type",
        default="percentage",
    )
    advance_payment_value = fields.Float(
        string="Advance Payment Value",
        help="The value of the advance payment"
    )
    advance_payment_percentage = fields.Float(
        string="Advance Payment %",
        help="The percentage of the advance payment"
    )
    # -=-=-=-=-=-=-=-=-=-=-=-=-=-=-=--=-=-=-=-=-=-=-=-=-=-=-=

    service_ids = fields.Many2many(
        "hotel.service",
        string="Services",
        compute="_compute_services_facilities",
        store=True
    )
    facility_ids = fields.Many2many(
        "hotel.facility",
        string="Facilities",
        compute="_compute_services_facilities",
        store=True
    )
    review_display_limit = fields.Integer(
        string="Review Display Limit",
        default=10,
        help="Number of reviews to display on the website frontend."
    )

    @api.depends('room_ids.service_ids', 'room_ids.facility_ids')
    def _compute_services_facilities(self):
        for hotel in self:
            services = hotel.room_ids.mapped('service_ids')
            facilities = hotel.room_ids.mapped('facility_ids')
            hotel.service_ids = services
            hotel.facility_ids = facilities

    def action_toggle_is_published(self):
        """Toggle the field `is_published`.

        :return: None
        """
        if not self.room_ids:
            raise UserError(_("No room belongs to this Hotel yet"))
        self.is_published = not self.is_published

    def action_go_to_website(self):
        base_url = request.env["ir.config_parameter"].sudo(
        ).get_param("web.base.url")
        hotel_url = f"{base_url}/hotel/{self.id}"
        return {
            "type": "ir.actions.act_url",
            "url": hotel_url,
            "target": "new",
        }

    def action_open_add_rooms_wizard(self):
        """
        Open the wizard to add rooms.
        """
        return {
            "name": "Add Rooms",
            "type": "ir.actions.act_window",
            "res_model": "hotel.add.rooms.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_hotel_id": self.id},
        }

    def check_cart_product(self, website_id, hotel_id):
        """
        Existing rooms in cart validation.
        """
        website = self.env["website"].browse(website_id)
        sale_order = website.sale_get_order()
        session_hotel_id = request.session.get("hotel_id")

        if session_hotel_id and sale_order and sale_order.order_line:
            if session_hotel_id == int(hotel_id):
                return True
            else:
                return False
        return True

    def flushCart(self, website_id, hotel_id):
        """
        Flush the cart
        """
        website = self.env["website"].browse(website_id)
        sale_order = website.sale_get_order()
        request.session["hotel_id"] = int(hotel_id)
        if sale_order and sale_order.order_line:
            sale_order.order_line = None
        return True

    def action_view_rating(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'hotel_management_system.rating_rating_action_hotel_report')
        action['context'] = {'search_default_parent_res_name': self.name}
        return action

    def action_open_rooms_list(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Hotel Rooms',
            'res_model': 'product.template',
            'view_mode': 'kanban,tree,form',
            'domain': [('hotel_id', '=', self.id)],
            'context': {
                'default_hotel_id': self.id,
                'search_default_hotel_id': self.id,
            },
        }

    def _rating_get_repartition(self, add_stats=False, domain=None):
        base_domain = expression.AND(
            [self._rating_domain(), [('rating', '>=', 1)]])
        if domain:
            base_domain += domain
        rg_data = self.env['rating.rating']._read_group(
            base_domain, ['rating'], ['__count'])
        values = dict.fromkeys(range(1, 6), 0)
        for rating, count in rg_data:
            rating_val_round = float_round(rating, precision_digits=1)
            values[rating_val_round] = values.get(rating_val_round, 0) + count
        if add_stats:
            rating_number = sum(values.values())
            return {
                'repartition': values,
                'avg': sum(float(key * values[key]) for key in values) / rating_number if rating_number > 0 else 0,
                'total': sum(count for __, count in rg_data),
            }
        return values

    def rating_get_grades(self, domain=None):
        data = self._rating_get_repartition(domain=domain)
        res = dict.fromkeys(['great', 'okay', 'bad'], 0)
        for key in data:
            grade = rating_data._rating_to_grade(key)
            res[grade] += data[key]
        return res

    def rating_get_stats(self, domain=None):
        data = self._rating_get_repartition(domain=domain, add_stats=True)
        result = {
            'avg': data['avg'],
            'total': data['total'],
            'percent': dict.fromkeys(range(1, 6), 0),
        }
        for rate in data['repartition']:
            result['percent'][rate] = (
                data['repartition'][rate] * 100) / data['total'] if data['total'] > 0 else 0
        return result

    def _rating_domain(self):
        return ['&', '&', ('res_model', '=', self._name), ('res_id', 'in', self.ids), ('consumed', '=', True)]


class HotelType(models.Model):
    _name = "hotel.type"
    _description = "Hotel Type"
    _rec_name = "hotel_type"

    hotel_type = fields.Char("Hotel Type")


class RatingRating(models.Model):
    _inherit = 'rating.rating'

    def _find_parent_data(self, values):
        model_name = self.env['ir.model'].sudo().browse(
            values['res_model_id']).model

        if model_name == 'hotel.hotels':
            record = self.env[model_name].browse(values['res_id'])
            return {
                'parent_res_model_id': self.env['ir.model']._get(model_name).id,
                'parent_res_id': record.id,
            }

        return super()._find_parent_data(values)
