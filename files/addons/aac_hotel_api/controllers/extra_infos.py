# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response
from odoo.tools import json_default
from odoo.exceptions import ValidationError, AccessError
from .api_auth import validate_api_key

_logger = logging.getLogger(__name__)

class HotelExtraInfosController(http.Controller):
    """Controlador para información adicional de reservas"""

    def _prepare_response(self, data, status=200):
        """Preparar respuesta JSON"""
        return Response(
            json.dumps(data, default=json_default),
            status=status,
            content_type='application/json'
        )

    # =============================================================================
    # ENDPOINTS PARA INFORMACIÓN ADICIONAL (EXTRA INFOS)
    # =============================================================================

    @http.route('/api/hotel/booking/<int:booking_id>/extra_infos', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_extra_infos(self, booking_id, **kw):
        """Obtener información adicional de una reserva"""
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Reserva con ID {booking_id} no encontrada'
                }, status=404)
            
            # Obtener información adicional
            extra_infos = {
                'booking_id': booking_id,
                'booking_reference': booking.sequence_id,
                'booking_date': booking.booking_date,
                'booking_days': booking.booking_days,
                'remarks': booking.description or '',
                'company': {
                    'id': booking.company_id.id,
                    'name': booking.company_id.name,
                },
                'status_bar': booking.status_bar,
                'check_in': booking.check_in,
                'check_out': booking.check_out,
                'partner': {
                    'id': booking.partner_id.id,
                    'name': booking.partner_id.name,
                    'email': booking.partner_id.email,
                    'phone': booking.partner_id.phone,
                },
                'hotel': {
                    'id': booking.hotel_id.id if booking.hotel_id else None,
                    'name': booking.hotel_id.name if booking.hotel_id else None,
                },
                'user_id': {
                    'id': booking.user_id.id,
                    'name': booking.user_id.name,
                },
                'currency': {
                    'id': booking.currency_id.id,
                    'name': booking.currency_id.name,
                    'symbol': booking.currency_id.symbol,
                },
                'total_amount': booking.total_amount,
                'create_date': booking.create_date,
                'write_date': booking.write_date,
            }
            
            _logger.info(f"Información adicional obtenida para reserva {booking_id}")
            
            return self._prepare_response({
                'success': True,
                'data': extra_infos
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_extra_infos: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/booking/<int:booking_id>/extra_infos', auth='public', type='http', methods=['PUT'], csrf=False)
    @validate_api_key
    def update_extra_infos(self, booking_id, **kw):
        """Actualizar información adicional de una reserva"""
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Reserva con ID {booking_id} no encontrada'
                }, status=404)
            
            # Obtener datos del JSON
            data = {}
            try:
                if request.httprequest.data:
                    data = json.loads(request.httprequest.data.decode('utf-8'))
            except:
                pass
            
            # Preparar valores para actualización
            update_vals = {}
            
            # Campos que se pueden actualizar
            updatable_fields = [
                'booking_date', 'booking_days', 'description', 'company_id',
                'user_id', 'hotel_id', 'partner_id'
            ]
            
            for field in updatable_fields:
                if field in data:
                    update_vals[field] = data[field]
            
            # Validaciones específicas
            if 'booking_days' in update_vals:
                if update_vals['booking_days'] < 0:
                    return self._prepare_response({
                        'success': False,
                        'error': 'Los días de reserva no pueden ser negativos'
                    }, status=400)
            
            if 'booking_date' in update_vals:
                try:
                    # Convertir string a datetime si es necesario
                    if isinstance(update_vals['booking_date'], str):
                        from datetime import datetime
                        update_vals['booking_date'] = datetime.fromisoformat(
                            update_vals['booking_date'].replace('T', ' ')
                        )
                except ValueError:
                    return self._prepare_response({
                        'success': False,
                        'error': 'Formato de fecha inválido'
                    }, status=400)
            
            # Actualizar la reserva si hay cambios
            if update_vals:
                booking.write(update_vals)
            
            # Obtener información actualizada
            updated_extra_infos = {
                'booking_id': booking_id,
                'booking_reference': booking.sequence_id,
                'booking_date': booking.booking_date,
                'booking_days': booking.booking_days,
                'remarks': booking.description or '',
                'company': {
                    'id': booking.company_id.id,
                    'name': booking.company_id.name,
                },
                'status_bar': booking.status_bar,
                'check_in': booking.check_in,
                'check_out': booking.check_out,
                'partner': {
                    'id': booking.partner_id.id,
                    'name': booking.partner_id.name,
                    'email': booking.partner_id.email,
                    'phone': booking.partner_id.phone,
                },
                'hotel': {
                    'id': booking.hotel_id.id if booking.hotel_id else None,
                    'name': booking.hotel_id.name if booking.hotel_id else None,
                },
                'user_id': {
                    'id': booking.user_id.id,
                    'name': booking.user_id.name,
                },
                'currency': {
                    'id': booking.currency_id.id,
                    'name': booking.currency_id.name,
                    'symbol': booking.currency_id.symbol,
                },
                'total_amount': booking.total_amount,
                'create_date': booking.create_date,
                'write_date': booking.write_date,
            }
            
            _logger.info(f"Información adicional actualizada para reserva {booking_id}")
            
            return self._prepare_response({
                'success': True,
                'message': 'Información adicional actualizada exitosamente',
                'data': updated_extra_infos
            })
            
        except ValidationError as e:
            _logger.error(f"Error de validación en update_extra_infos: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': str(e)
            }, status=400)
        except Exception as e:
            _logger.exception(f"Error inesperado en update_extra_infos: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/booking/<int:booking_id>/extra_infos/remarks', auth='public', type='http', methods=['POST'], csrf=False)
    @validate_api_key
    def update_remarks(self, booking_id, **kw):
        """Actualizar solo las observaciones/notas de una reserva"""
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Reserva con ID {booking_id} no encontrada'
                }, status=404)
            
            # Obtener datos del JSON
            data = {}
            try:
                if request.httprequest.data:
                    data = json.loads(request.httprequest.data.decode('utf-8'))
            except:
                pass
            
            if 'remarks' not in data:
                return self._prepare_response({
                    'success': False,
                    'error': 'El campo remarks es requerido'
                }, status=400)
            
            # Actualizar solo las observaciones
            booking.write({
                'description': data['remarks']
            })
            
            _logger.info(f"Observaciones actualizadas para reserva {booking_id}")
            
            return self._prepare_response({
                'success': True,
                'message': 'Observaciones actualizadas exitosamente',
                'data': {
                    'booking_id': booking_id,
                    'booking_reference': booking.sequence_id,
                    'remarks': booking.description or '',
                    'updated_at': booking.write_date
                }
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en update_remarks: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/booking/<int:booking_id>/extra_infos/company', auth='public', type='http', methods=['POST'], csrf=False)
    @validate_api_key
    def update_company(self, booking_id, **kw):
        """Actualizar solo la empresa de una reserva"""
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Reserva con ID {booking_id} no encontrada'
                }, status=404)
            
            # Obtener datos del JSON
            data = {}
            try:
                if request.httprequest.data:
                    data = json.loads(request.httprequest.data.decode('utf-8'))
            except:
                pass
            
            if 'company_id' not in data:
                return self._prepare_response({
                    'success': False,
                    'error': 'El campo company_id es requerido'
                }, status=400)
            
            # Validar que la empresa exista
            company = request.env['res.company'].browse(data['company_id'])
            if not company.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Empresa con ID {data["company_id"]} no encontrada'
                }, status=404)
            
            # Actualizar solo la empresa
            booking.write({
                'company_id': data['company_id']
            })
            
            _logger.info(f"Empresa actualizada para reserva {booking_id}: {company.name}")
            
            return self._prepare_response({
                'success': True,
                'message': 'Empresa actualizada exitosamente',
                'data': {
                    'booking_id': booking_id,
                    'booking_reference': booking.sequence_id,
                    'company': {
                        'id': booking.company_id.id,
                        'name': booking.company_id.name,
                    },
                    'updated_at': booking.write_date
                }
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en update_company: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)
