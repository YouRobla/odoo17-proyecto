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
    "name": "Odoo Hotel Booking Channel Manager",
    "summary": """Odoo Hotel Booking Channel Manager simplifies hotel booking management by syncing rates, inventory, and availability across multiple OTAs. It connects Odoo with QloApps, ensuring real-time updates and reducing manual efforts. With centralized booking management, hoteliers can prevent overbookings and inventory mismatches.
                This improves operational efficiency, enhances guest experience, and helps maintain a strong online reputation.  QLoApps Channel Manager | Hotel Channel Manager | Hotel Management System | booking.com | expedia | goibibo | makemytrip | google hotel | agoda | despegar | yatra | bakuun | airbnb
                """,
    "author": "Webkul Software Pvt. Ltd.",
    "depends": ["hotel_management_system"],
    "category": "Generic Modules/Hotel Reservation",
    "version": "1.0.0",
    "sequence": 1,
    "license": "Other proprietary",
    "website": "https://store.webkul.com/",
    "description": """Odoo Hotel Booking Channel Manager syncs OTA bookings with Odoo, updating availability and rates in real time to prevent overbookings. It automates booking management, reducing manual effort and errors. With a centralized dashboard, you can track and manage all reservations easily. Seamless integration with Odoo ensures accurate inventory and pricing across all platforms.
                        QLoApps Channel Manager
                        Hotel Channel Manager
                        Hotel Management System
                        Odoo Hotel Management
                        Ota Channel Manager
                    """,
    "live_test_url": "https://qloapps.com/channel-manager",
    "data": [
        "security/ir.model.access.csv",
        "views/hotel_rest_api_views.xml",
    ],
    "demo": [],
    "images": ["static/description/banner.gif"],
    "assets": {},
    "application": True,
    "installable": True,
    "auto_install": False,
    "pre_init_hook": "pre_init_check",
}
