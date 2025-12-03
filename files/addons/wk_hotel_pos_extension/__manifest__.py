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
{
    "name": "Hotel POS Extension",
    "summary": "Odoo POS Restaurant Extension connects Odoo POS with Odoo Hotel Management. This module lets customers place room service orders which will be paid on checkout. The Odoo app eases billing by providing combined or isolated bills during checkout. The module generates POS invoices for every room order that customers can verify and pay at checkout.",
    "author":  "Webkul Software Pvt. Ltd.",
    "maintainer":  "Webkul Software Pvt. Ltd.",
    "depends": ['hotel_management_system', 'point_of_sale'],
    "category":  "Point of Sale",
    "version":  "1.0.2",
    "sequence":  1,
    "license":  "Other proprietary",
    "website":  "https://store.webkul.com/odoo-hotel-pos-extension.html",
    "description":  " Odoo Hotel POS Restaurant Extension allows you to generate POS invoices for room bills which you can print later on with room bills in a computed or isolated form.",
    "live_test_url":  "https://odoodemo.webkul.in/demo_feedback?module=wk_hotel_pos_extension",
    "data": [
        'report/booking_report_templates.xml',
        'views/view_hotel_booking.xml',
        'wizard/view_compute_bill.xml',
    ],
    "images":  ['static/description/banner.png'],
    "assets": {
        'point_of_sale._assets_pos': [
            'wk_hotel_pos_extension/static/src/js/*.js',
            'wk_hotel_pos_extension/static/src/js/**/*.js',
            'wk_hotel_pos_extension/static/src/xml/*.xml',
        ]
    },
    "application":  False,
    "installable":  True,
    "price":  99,
    "currency":  "USD",
    "auto_install":  False,
    "pre_init_hook":  "pre_init_check",
}
