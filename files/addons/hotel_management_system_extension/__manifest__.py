# -*- coding: utf-8 -*-
{
    "name": "Hotel Management System - Extension",
    "summary": "Extensión del sistema de gestión hotelera con componentes Gantt y Calendar",
    "description": """
        Este módulo extiende el sistema de gestión hotelera con:
        - Vista Gantt avanzada para reservas
        - Vista de calendario para el dashboard
        - Componentes JavaScript personalizados
    """,
    "author": "Hotel Management Team",
    "category": "Generic Modules/Hotel Reservation",
    "version": "1.0.0",
    "depends": [
        "hotel_management_system",
        "web",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/product_data.xml",
        "data/mail_template_data.xml",
        "views/calendar_views.xml",
        "views/hotel_booking_extension_views.xml",
        "views/price_change_wizard_views.xml",
        "views/change_room_wizard_views.xml",
        "views/booking_bill_extension_views.xml",
        "views/res_partner_views.xml",
    ],
            "assets": {
                "web.assets_backend": [
                    "hotel_management_system_extension/static/src/components/room_panel/room_panel.scss",
                    "hotel_management_system_extension/static/src/components/room_panel/room_panel.xml",
                    "hotel_management_system_extension/static/src/components/room_panel/room_panel.js",
                    "hotel_management_system_extension/static/src/components/reservation_gantt/reservation_gantt.scss",
                    "hotel_management_system_extension/static/src/components/reservation_gantt/reservation_gantt.js",
                ],
            },
    "application": False,
    "installable": True,
    "auto_install": False,
    "license": "LGPL-3",
} 