# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2024 Hotel Management System Extension
# See LICENSE file for full copyright and licensing details.
##############################################################################

from odoo import models, api


class ComputeBillExtension(models.TransientModel):
    _inherit = 'booking.bill'

    def _get_booking_id(self, booking_id):
        """
        Sobrescribir para asegurar que el contexto se pase correctamente
        a las órdenes de venta relacionadas
        """
        order_ids = self.env["sale.order"].search(
            [("booking_id", "=", booking_id.id), ("state", "=", "sale")]
        )
        if booking_id.order_id.id not in order_ids.ids:
            order_ids += booking_id.order_id
        
        # Asegurar que todas las órdenes tengan el contexto de Print Bill
        for order in order_ids:
            order = order.with_context(is_print_bill_context=True)
        
        return order_ids

    def print_detailed_report(self):
        """
        Sobrescribir para asegurar que el contexto se pase correctamente
        """
        booking_id = self.env["hotel.booking"].browse(self._context.get("active_ids"))
        self.booking_id = booking_id.id
        self.partner_id = booking_id.partner_id.id
        self._generate_room_bill_info()
        self.order_ids = self._get_booking_id(booking_id)
        
        # Asegurar que el contexto se pase a la acción del reporte
        action = self.env.ref(
            "hotel_management_system.action_report_booking_detailed_bill"
        ).report_action(self)
        
        # Agregar el contexto de Print Bill si no está presente
        if 'context' not in action:
            action['context'] = {}
        action['context']['is_print_bill_context'] = True
        
        return action

    def print_report(self):
        """
        Sobrescribir para asegurar que el contexto se pase correctamente
        """
        booking_id = self.env["hotel.booking"].browse(self._context.get("active_ids"))
        self.booking_id = booking_id.id
        self.partner_id = booking_id.partner_id.id
        self._generate_room_bill_info()

        if self.print_bill != "combine":    
            self.order_ids = self._get_booking_id(booking_id)
            action = self.env.ref(
                "hotel_management_system.action_report_booking_separate"
            ).report_action(self)
        else:
            self.order_ids = self._get_booking_id(booking_id)
            action = self.env.ref(
                "hotel_management_system.action_report_booking_combine"
            ).report_action(self)
        
        # Asegurar que el contexto se pase a la acción del reporte
        if 'context' not in action:
            action['context'] = {}
        action['context']['is_print_bill_context'] = True
        
        return action
