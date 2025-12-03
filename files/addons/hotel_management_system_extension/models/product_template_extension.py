# -*- coding: utf-8 -*-
"""
Extensiones para el modelo product.template para el panel de habitaciones
"""

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class ProductTemplateRoomPanel(models.Model):
    """
    Extensiones para product.template para el panel de habitaciones
    """
    _inherit = 'product.template'

    # Campos adicionales para habitaciones
    room_floor = fields.Char(
        string='Piso',
        help="Piso donde se encuentra la habitación"
    )
    
    room_capacity = fields.Integer(
        string='Capacidad',
        default=2,
        help="Número máximo de huéspedes"
    )
    
    room_features_description = fields.Text(
        string='Características',
        help="Descripción de características especiales"
    )
    
    # Campo computado para obtener el estado inferido de reservas
    computed_room_status = fields.Selection([
        ('available', 'Disponible'),
        ('occupied', 'Ocupada'),
        ('dirty', 'Necesita limpieza'),
        ('maintenance', 'Mantenimiento')
    ], string='Estado Inferido', compute='_compute_room_status', store=False)
    
    @api.depends('is_room_type')
    def _compute_room_status(self):
        """
        Computar estado de habitación basado en reservas activas
        """
        for room in self:
            if not room.is_room_type:
                room.computed_room_status = False
                continue
                
            try:
                today = fields.Date.today()
                
                # Buscar reserva activa usando los estados del hotel_booking_extension.py
                active_booking = self.env['hotel.booking'].search([
                    ('booking_line_ids.product_id', '=', room.id),
                    ('check_in', '<=', today),
                    ('check_out', '>=', today),
                    ('status_bar', 'in', ['confirmed', 'checkin', 'checkout', 'cleaning_needed', 'room_ready'])
                ], limit=1)
                
                if active_booking:
                    if active_booking.status_bar == 'checkin':
                        room.computed_room_status = 'occupied'
                    elif active_booking.status_bar in ['checkout', 'cleaning_needed']:
                        room.computed_room_status = 'dirty'
                    elif active_booking.status_bar == 'room_ready':
                        room.computed_room_status = 'available'
                    else:
                        room.computed_room_status = 'available'
                else:
                    room.computed_room_status = 'available'
                    
            except Exception as e:
                _logger.error(f"Error computing room status for room {room.id}: {str(e)}")
                room.computed_room_status = 'available'


class HotelRoomFeature(models.Model):
    """
    Características de habitaciones
    """
    _name = 'hotel.room.feature'
    _description = 'Características de Habitación'
    _order = 'name'

    name = fields.Char(string='Característica', required=True)
    description = fields.Text(string='Descripción')
    icon = fields.Char(string='Icono CSS', help="Clase CSS del icono (ej: fa-wifi)")
    color = fields.Char(string='Color', default='#007bff')
    active = fields.Boolean(string='Activo', default=True)

    def name_get(self):
        return [(record.id, record.name) for record in self]
