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
    "name": "A complete Hotel Management Solution in ODOO",
    "summary": '''Odoo Hotel Management Solution helps hotels run smoothly. It makes it easy to book rooms, automates tasks like cleaning and billing, and provides all the information hotel owners need in one place.
                This helps them manage bookings, staff, and guest services, making the hotel run more efficiently and ensuring guests have a great experience.
                Odoo Hotel Management Solution | Hotel Management Solution | Dashboard | Housekeeping
                ''',
    "author": "Webkul Software Pvt. Ltd.",
    "depends": [
        "account",
        "sale_management",
        "website_sale",
        "wk_wizard_messages",
        "web", # Asegúrate de que 'web' esté en las dependencias
    ],
    "category": "Generic Modules/Hotel Reservation",
    "version": "1.1.1",
    "sequence": 1,
    "license": "Other proprietary",
    "website": "https://store.webkul.com/odoo-hotel-management-system.html",
    "description": '''Odoo Hotel Management Solution helps hotels run smoothly. It makes it easy to book rooms, keep track of how well the hotel is doing, and automate tasks like cleaning and laundry.
                    It also helps with things like managing commissions for travel agents, sending invoices, and keeping guests updated. Plus, it makes it simple to find the right room for each guest, which improves overall guest satisfaction.
                    Odoo Hotel Management Solution | Hotel Management Solution | Dashboard | Housekeeping
                    ''',
    "live_test_url": "https://hotel-management-v18.odoo-apps-demo.webkul.in/",
    "data": [
        'data/ir_config_parameter.xml',
        "data/service_products.xml",
        "data/ir_sequence.xml",
        "data/adv_payment_mail_template.xml",
        "views/ir_cron.xml",
        "security/hotel_security.xml",
        "security/ir.model.access.csv",
        "report/booking_confirm.xml",
        "report/booking_allot.xml",
        "report/booking_cancel.xml",
        "report/exchange_room.xml",
        "report/booking_report.xml",
        "report/booking_report_templates.xml",
        'wizard/hotel_service_checkout_wizard.xml',
        "data/mail_template_data.xml",
        "views/hotel_feedback_templates.xml",
        "wizard/cancel_booking.xml",
        "wizard/exchange_room_views.xml",
        "views/hotel_booking_views.xml",
        "wizard/add_booking_room_views.xml",
        "views/hotel_keeping_views.xml",
        "views/hotel_service_views.xml",
        "views/res_config_settings_views.xml",
        "views/hotel_booking_line_views.xml",
        "views/hotel_facility_views.xml",
        "views/product_views.xml",
        "views/room_service_views.xml",
        "views/sale_order_views.xml",
        "views/account_view.xml",
        "views/guest_info.xml",
        "views/hotel_hotels_views.xml",
        "views/hotel_menu_items.xml",
        "views/account_payment.xml",
        "wizard/compute_bill_views.xml",
        "wizard/house_keeping_wizard.xml",
        "wizard/hotel_service_wizards.xml",
        "wizard/attached_doc_views.xml",
        "wizard/add_rooms.xml",
        "wizard/sale_order_cancel_custom.xml",
        "views/template.xml",
        "views/snippets/hotel_room_snippet.xml",
        "views/snippets/snippets.xml",
        "views/adv_snippet_options.xml",
        "views/adv_template.xml",
    ],
    "demo": ["data/hotel_demo.xml"],
    "images": ["static/description/banner.gif"],
    "assets": {
        "web.assets_frontend": [
            'hotel_management_system/static/src/scss/multi_hotel.scss',
            "hotel_management_system/static/src/swiper/swiper-bundle.min.css",
            "hotel_management_system/static/src/scss/style.scss",
            "hotel_management_system/static/src/snippets/s_hotel/000.scss",
            "hotel_management_system/static/src/snippets/s_hotel/000.js",
            "hotel_management_system/static/src/js/available_rooms.js",
            "hotel_management_system/static/src/js/feedback.js",

            # Advance Payment Integration
            "hotel_management_system/static/src/js/adv_payment_form_mixin.js",
            "hotel_management_system/static/src/js/adv_payment.js",
            "hotel_management_system/static/src/scss/adv_payment.scss",
            
            "hotel_management_system/static/src/xml/templates.xml",
        ],
        "web.assets_backend": [
            "hotel_management_system/static/src/scss/owner.scss",
            "hotel_management_system/static/src/xml/dashboard.xml",
            "hotel_management_system/static/src/js/dashboard.js",
            "hotel_management_system/static/src/chart/**/*",
            "hotel_management_system/static/src/views/**/*",
            "hotel_management_system/static/src/scss/dashboard.scss",
            

        ],
    },
    "application": True,
    "installable": True,
    "auto_install": False,
    "price": 299,
    "currency": "USD",
    "pre_init_hook": "pre_init_check",
}