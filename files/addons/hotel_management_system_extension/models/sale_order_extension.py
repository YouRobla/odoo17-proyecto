# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2024 Hotel Management System Extension
# See LICENSE file for full copyright and licensing details.
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrderExtension(models.Model):
    _inherit = 'sale.order'

    def _confirm_room_for_booking(self, room_type_booking_line):
        """
        Sobrescribir para evitar la validación problemática de fechas
        cuando se está generando una factura desde una reserva existente
        """
        # Si estamos en el contexto de generar factura (Print Bill), 
        # no hacer la validación de fechas ya que la reserva ya existe
        if self.env.context.get('is_print_bill_context'):
            # Solo verificar que las habitaciones no estén duplicadas en el mismo período
            # pero sin la validación estricta de fechas
            booking_rooms = room_type_booking_line.mapped("product_id")
            existing_bookings = self.env["hotel.booking"].search([
                ("status_bar", "not in", ["cancel", "checkout"]),
                ("booking_line_ids.product_id", "in", booking_rooms.ids),
            ])
            
            # Filtrar solo las reservas que realmente están en conflicto
            conflicting_bookings = self.env["hotel.booking"]
            for booking in existing_bookings:
                if booking.id != self.booking_id.id:  # Excluir la reserva actual
                    # Verificar si hay conflicto real de fechas
                    if (booking.check_in and booking.check_out and 
                        self.hotel_check_in and self.hotel_check_out):
                        # Solo hay conflicto si las fechas se solapan realmente
                        if not (booking.check_out <= self.hotel_check_in or 
                                booking.check_in >= self.hotel_check_out):
                            conflicting_bookings |= booking
            
            return conflicting_bookings
        
        # Si no es contexto de Print Bill, usar la lógica original del módulo padre
        return super()._confirm_room_for_booking(room_type_booking_line)


class SaleOrderLineExtension(models.Model):
    _inherit = 'sale.order.line'
    
    # Agregar campo tax_id para compatibilidad con módulo padre
    # El módulo padre usa "tax_id": line.tax_ids pero este campo no existe en Odoo estándar
    tax_id = fields.Many2many('account.tax', string='Taxes (Legacy)', 
                             help='Campo de compatibilidad con módulo padre')
