# -*- coding: utf-8 -*-
import json
import logging
from odoo import http
from odoo.http import request, Response
from odoo.tools import json_default
from odoo.exceptions import ValidationError, AccessError
from .api_auth import validate_api_key

_logger = logging.getLogger(__name__)

class HotelInformacionPreciosController(http.Controller):
    """Controlador especializado para información de precios de reservas"""

    def _prepare_response(self, data, status=200):
        """Preparar respuesta JSON"""
        return Response(
            json.dumps(data, default=json_default),
            status=status,
            content_type='application/json'
        )

    def _build_price_info(self, booking):
        """Construir información completa de precios de una reserva"""
        # Obtener precio original del modelo
        original_price = booking.original_price or 0.0
        # new_price es el precio actual sin impuestos (amount_untaxed)
        new_price = booking.amount_untaxed or 0.0
        total_amount = booking.total_amount or 0.0
        
        # Calcular descuento: diferencia entre precio original y nuevo precio
        discount_amount = max(0.0, original_price - new_price)
        
        price_info = {
            'booking_id': booking.id,
            'booking_reference': booking.sequence_id,
            'status_bar': booking.status_bar,
            
            # Montos principales
            'total_amount': total_amount,
            'amount_untaxed': booking.amount_untaxed,
            'tax_amount': booking.tax_amount,
            'additional_charges_total': getattr(booking, 'additional_charges_total', 0.0),
            
            # Precios originales y descuentos
            'original_price': original_price,
            'discount_amount': discount_amount,
            'discount_reason': booking.discount_reason,
            
            # Cargos adicionales
            'early_checkin_charge': booking.early_checkin_charge,
            'late_checkout_charge': booking.late_checkout_charge,
            
            # Servicios manuales
            'manual_service_description': booking.manual_service_description,
            'manual_service_amount': booking.manual_service_amount,
            
            # Información de moneda y lista de precios
            'currency': {
                'id': booking.currency_id.id if booking.currency_id else None,
                'name': booking.currency_id.name if booking.currency_id else None,
                'symbol': booking.currency_id.symbol if booking.currency_id else '$',
            } if booking.currency_id else None,
            'pricelist': {
                'id': booking.pricelist_id.id if booking.pricelist_id else None,
                'name': booking.pricelist_id.name if booking.pricelist_id else None,
            } if booking.pricelist_id else None,
            
            # Desglose por habitaciones
            'room_prices': self._build_room_price_breakdown(booking.booking_line_ids),
            
            # Servicios adicionales
            'services': self._build_services_data(getattr(booking, 'hotel_service_lines', [])),
            
            # Resumen financiero
            'financial_summary': self._build_financial_summary(booking),
            
            # Fechas de cálculo
            'calculated_at': booking.write_date,
        }
        
        return price_info

    def _build_room_price_breakdown(self, booking_lines):
        """Construir desglose de precios por habitación"""
        room_prices = []
        
        for line in booking_lines:
            room_price_info = {
                'line_id': line.id,
                'booking_sequence_id': line.booking_sequence_id,
                'room_name': line.product_id.name,
                'room_id': line.product_id.id,
                
                # Precios de la habitación
                'price_per_night': line.price,
                'original_price_per_night': getattr(line, 'original_price', line.price),
                'discount_percentage': line.discount,
                'discount_amount_per_night': getattr(line, 'original_price', line.price) - line.price,
                'discount_reason': getattr(line, 'discount_reason', ''),
                
                # Cálculos por días
                'booking_days': line.booking_days,
                'subtotal_price': line.subtotal_price,
                'taxed_price': line.taxed_price,
                
                # Impuestos
                'tax_ids': line.tax_ids.ids,
                'tax_names': [tax.name for tax in line.tax_ids],
                'tax_rate': sum(tax.amount for tax in line.tax_ids),
                
                # Capacidad
                'max_adult': line.max_adult,
                'max_child': line.max_child,
                'current_guests': len(line.guest_info_ids),
            }
            room_prices.append(room_price_info)
        
        return room_prices

    def _build_services_data(self, service_lines):
        """Construir datos de servicios adicionales"""
        services = []
        
        for service in service_lines:
            service_data = {
                'id': service.id,
                'service_id': service.service_id.id if service.service_id else None,
                'service_name': service.service_id.name if service.service_id else 'Servicio Manual',
                'amount': service.amount,
                'note': service.note or '',
                'create_date': service.create_date,
            }
            services.append(service_data)
        
        return services

    def _build_financial_summary(self, booking):
        """Construir resumen financiero de la reserva"""
        # Calcular totales
        rooms_subtotal = sum(line.subtotal_price for line in booking.booking_line_ids)
        rooms_taxed = sum(line.taxed_price for line in booking.booking_line_ids)
        
        additional_charges = (booking.early_checkin_charge or 0) + (booking.late_checkout_charge or 0)
        manual_services = booking.manual_service_amount or 0
        
        # Calcular descuento: diferencia entre precio original y nuevo precio (amount_untaxed)
        original_price = booking.original_price or rooms_subtotal
        new_price = booking.amount_untaxed or 0.0
        total_discount = max(0.0, original_price - new_price)
        total_original = original_price
        
        return {
            'rooms_subtotal': rooms_subtotal,
            'rooms_taxed': rooms_taxed,
            'additional_charges': additional_charges,
            'manual_services': manual_services,
            'total_discount': total_discount,
            'total_original': total_original,
            'final_total': booking.total_amount,
            'savings_percentage': (total_discount / total_original * 100) if total_original > 0 else 0,
        }

    # =============================================================================
    # ENDPOINTS PARA INFORMACIÓN DE PRECIOS
    # =============================================================================

    @http.route('/api/hotel/booking/<int:booking_id>/price_info', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_price_info(self, booking_id, **kw):
        """Obtener información completa de precios de una reserva"""
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Reserva con ID {booking_id} no encontrada'
                }, status=404)
            
            price_info = self._build_price_info(booking)
            
            _logger.info(f"Información de precios obtenida para reserva {booking_id}")
            
            return self._prepare_response({
                'success': True,
                'data': price_info
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_price_info: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/booking/<int:booking_id>/price_breakdown', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_price_breakdown(self, booking_id, **kw):
        """Obtener desglose detallado de precios"""
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Reserva con ID {booking_id} no encontrada'
                }, status=404)
            
            breakdown = {
                'booking_id': booking_id,
                'booking_reference': booking.sequence_id,
                'room_breakdown': self._build_room_price_breakdown(booking.booking_line_ids),
                'services_breakdown': self._build_services_data(getattr(booking, 'hotel_service_lines', [])),
                'financial_summary': self._build_financial_summary(booking),
            }
            
            _logger.info(f"Desglose de precios obtenido para reserva {booking_id}")
            
            return self._prepare_response({
                'success': True,
                'data': breakdown
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_price_breakdown: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/booking/<int:booking_id>/price_info', auth='public', type='http', methods=['PUT'], csrf=False)
    @validate_api_key
    def update_price_info(self, booking_id, **kw):
        """Actualizar campos específicos de precios de una reserva"""
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
            
            # Campos de precios que se pueden actualizar
            price_fields = [
                'discount_reason', 'early_checkin_charge', 'late_checkout_charge',
                'manual_service_description', 'manual_service_amount'
            ]
            
            for field in price_fields:
                if field in data:
                    update_vals[field] = data[field]
            
            # Validaciones específicas
            if 'early_checkin_charge' in update_vals:
                if update_vals['early_checkin_charge'] < 0:
                    return self._prepare_response({
                        'success': False,
                        'error': 'El cargo por check-in temprano no puede ser negativo'
                    }, status=400)
            
            if 'late_checkout_charge' in update_vals:
                if update_vals['late_checkout_charge'] < 0:
                    return self._prepare_response({
                        'success': False,
                        'error': 'El cargo por check-out tardío no puede ser negativo'
                    }, status=400)
            
            if 'manual_service_amount' in update_vals:
                if update_vals['manual_service_amount'] < 0:
                    return self._prepare_response({
                        'success': False,
                        'error': 'El monto del servicio manual no puede ser negativo'
                    }, status=400)
            
            # Actualizar la reserva si hay cambios
            if update_vals:
                booking.write(update_vals)
            
            # Obtener información actualizada
            updated_price_info = self._build_price_info(booking)
            
            _logger.info(f"Información de precios actualizada para reserva {booking_id}")
            
            return self._prepare_response({
                'success': True,
                'message': 'Información de precios actualizada exitosamente',
                'data': updated_price_info
            })
            
        except ValidationError as e:
            _logger.error(f"Error de validación en update_price_info: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': str(e)
            }, status=400)
        except Exception as e:
            _logger.exception(f"Error inesperado en update_price_info: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/booking/<int:booking_id>/price_info/recalculate', auth='public', type='http', methods=['POST'], csrf=False)
    @validate_api_key
    def recalculate_prices(self, booking_id, **kw):
        """Recalcular todos los precios de una reserva"""
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Reserva con ID {booking_id} no encontrada'
                }, status=404)
            
            # Forzar recálculo de montos
            booking._compute_actual_amount()
            
            # Recalcular precios originales y descuentos
            if hasattr(booking, '_compute_original_price'):
                booking._compute_original_price()
            if hasattr(booking, '_compute_discount_amount'):
                booking._compute_discount_amount()
            
            # Recalcular cargos adicionales
            if hasattr(booking, '_compute_additional_charges_total'):
                booking._compute_additional_charges_total()
            
            # Obtener información recalculada
            recalculated_price_info = self._build_price_info(booking)
            
            _logger.info(f"Precios recalculados para reserva {booking_id}")
            
            return self._prepare_response({
                'success': True,
                'message': 'Precios recalculados exitosamente',
                'data': recalculated_price_info
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en recalculate_prices: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/booking/<int:booking_id>/price_history', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_price_history(self, booking_id, **kw):
        """Obtener historial de cambios de precios de una reserva"""
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Reserva con ID {booking_id} no encontrada'
                }, status=404)
            
            # Por ahora devolvemos información básica del historial
            # En el futuro se puede implementar un modelo específico para tracking de precios
            history = {
                'booking_id': booking_id,
                'booking_reference': booking.sequence_id,
                'current_price_info': self._build_price_info(booking),
                'created_at': booking.create_date,
                'last_updated': booking.write_date,
                'note': 'Historial completo de cambios de precios disponible en futuras versiones'
            }
            
            _logger.info(f"Historial de precios obtenido para reserva {booking_id}")
            
            return self._prepare_response({
                'success': True,
                'data': history
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_price_history: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    # =============================================================================
    # ENDPOINTS POR USUARIO PARA INFORMACIÓN DE PRECIOS
    # =============================================================================


    @http.route('/api/hotel/user/<int:user_id>/price_summary', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_user_price_summary(self, user_id, **kw):
        """Obtener resumen financiero de un usuario"""
        try:
            # Verificar que el usuario existe
            user = request.env['res.users'].browse(user_id)
            if not user.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Usuario con ID {user_id} no encontrado'
                }, status=404)
            
            # Buscar reservas del usuario
            domain = [('partner_id', '=', user_id)]
            
            # Aplicar filtro por huésped si se especifica
            if kw.get('guest_id'):
                domain.append(('booking_line_ids.guest_info_ids', '=', int(kw['guest_id'])))
            
            booking_records = request.env['hotel.booking'].search(domain)
            
            # Calcular estadísticas
            stats = {
                'total_reservas': len(booking_records),
                'total_amount': 0,
                'total_discount': 0,
                'total_original': 0,
                'by_status': {},
                'by_month': {},
            }
            
            for booking in booking_records:
                stats['total_amount'] += booking.total_amount
                stats['total_discount'] += booking.discount_amount or 0
                stats['total_original'] += booking.original_price or booking.total_amount
                
                # Por estado
                status = booking.status_bar
                if status not in stats['by_status']:
                    stats['by_status'][status] = {'count': 0, 'amount': 0}
                stats['by_status'][status]['count'] += 1
                stats['by_status'][status]['amount'] += booking.total_amount
                
                # Por mes
                month_key = booking.create_date.strftime('%Y-%m')
                if month_key not in stats['by_month']:
                    stats['by_month'][month_key] = {'count': 0, 'amount': 0}
                stats['by_month'][month_key]['count'] += 1
                stats['by_month'][month_key]['amount'] += booking.total_amount
            
            # Calcular porcentajes
            stats['savings_percentage'] = (stats['total_discount'] / stats['total_original'] * 100) if stats['total_original'] > 0 else 0
            stats['average_amount'] = stats['total_amount'] / stats['total_reservas'] if stats['total_reservas'] > 0 else 0
            
            _logger.info(f"Resumen financiero obtenido para usuario {user_id}")
            
            return self._prepare_response({
                'success': True,
                'data': {
                    'user_id': user_id,
                    'user_name': user.name,
                    'summary': stats
                }
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_user_price_summary: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/user/<int:user_id>/price_breakdown', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_user_price_breakdown(self, user_id, **kw):
        """Obtener desglose detallado de precios de todas las reservas de un usuario"""
        try:
            # Verificar que el usuario existe
            user = request.env['res.users'].browse(user_id)
            if not user.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Usuario con ID {user_id} no encontrado'
                }, status=404)
            
            # Buscar reservas del usuario con filtros
            domain = [('partner_id', '=', user_id)]
            
            # Aplicar filtros
            if kw.get('status_bar'):
                domain.append(('status_bar', '=', kw.get('status_bar')))
            if kw.get('date_from'):
                domain.append(('check_in', '>=', kw.get('date_from')))
            if kw.get('date_to'):
                domain.append(('check_out', '<=', kw.get('date_to')))
            if kw.get('hotel_id'):
                domain.append(('hotel_id', '=', int(kw['hotel_id'])))
            if kw.get('guest_id'):
                domain.append(('booking_line_ids.guest_info_ids', '=', int(kw['guest_id'])))
            
            booking_records = request.env['hotel.booking'].search(domain)
            
            # Construir desglose detallado
            breakdown_data = []
            total_stats = {
                'total_reservas': len(booking_records),
                'total_amount': 0.0,
                'total_discount': 0.0,
                'total_rooms': 0,
                'total_services': 0,
            }
            
            for booking in booking_records:
                booking_breakdown = {
                    'booking_id': booking.id,
                    'booking_reference': booking.sequence_id,
                    'status_bar': booking.status_bar,
                    'check_in': booking.check_in,
                    'check_out': booking.check_out,
                    'room_breakdown': self._build_room_price_breakdown(booking.booking_line_ids),
                    'services_breakdown': self._build_services_data(getattr(booking, 'hotel_service_lines', [])),
                    'financial_summary': self._build_financial_summary(booking),
                }
                
                breakdown_data.append(booking_breakdown)
                
                # Acumular estadísticas
                total_stats['total_amount'] += float(booking.total_amount)
                total_stats['total_discount'] += float(booking.discount_amount or 0)
                total_stats['total_rooms'] += len(booking.booking_line_ids)
                hotel_services = getattr(booking, 'hotel_service_lines', None)
                total_stats['total_services'] += len(hotel_services) if hotel_services else 0
            
            _logger.info(f"Desglose de precios obtenido para usuario {user_id}: {len(booking_records)} reservas")
            
            return self._prepare_response({
                'success': True,
                'data': {
                    'user_id': user_id,
                    'user_name': user.name,
                    'total_stats': total_stats,
                    'reservations_breakdown': breakdown_data
                }
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_user_price_breakdown: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/user/<int:user_id>/price_filters', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_user_price_filters(self, user_id, **kw):
        """Obtener opciones de filtros disponibles para un usuario"""
        try:
            # Verificar que el usuario existe
            user = request.env['res.users'].browse(user_id)
            if not user.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Usuario con ID {user_id} no encontrado'
                }, status=404)
            
            # Buscar reservas del usuario
            domain = [('partner_id', '=', user_id)]
            booking_records = request.env['hotel.booking'].search(domain)
            
            # Extraer opciones de filtros
            filter_options = {
                'status_options': list(set(booking.status_bar for booking in booking_records)),
                'hotel_options': [
                    {'id': booking.hotel_id.id, 'name': booking.hotel_id.name}
                    for booking in booking_records if booking.hotel_id
                ],
                'currency_options': [
                    {'id': booking.currency_id.id, 'name': booking.currency_id.name, 'symbol': booking.currency_id.symbol}
                    for booking in booking_records
                ],
                'amount_range': {
                    'min': min(booking.total_amount for booking in booking_records) if booking_records else 0,
                    'max': max(booking.total_amount for booking in booking_records) if booking_records else 0,
                },
                'date_range': {
                    'earliest': min(booking.check_in for booking in booking_records) if booking_records else None,
                    'latest': max(booking.check_out for booking in booking_records) if booking_records else None,
                },
                'discount_options': {
                    'has_discount': any(booking.discount_amount > 0 for booking in booking_records),
                    'no_discount': any(not booking.discount_amount or booking.discount_amount == 0 for booking in booking_records),
                }
            }
            
            # Eliminar duplicados en hoteles y monedas
            filter_options['hotel_options'] = list({h['id']: h for h in filter_options['hotel_options']}.values())
            filter_options['currency_options'] = list({c['id']: c for c in filter_options['currency_options']}.values())
            
            _logger.info(f"Opciones de filtros obtenidas para usuario {user_id}")
            
            return self._prepare_response({
                'success': True,
                'data': {
                    'user_id': user_id,
                    'user_name': user.name,
                    'total_reservas': len(booking_records),
                    'filter_options': filter_options
                }
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_user_price_filters: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/user/<int:user_id>/guests', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_user_guests(self, user_id, **kw):
        """Obtener lista de huéspedes de todas las reservas de un usuario"""
        try:
            # Verificar que el usuario existe
            user = request.env['res.users'].browse(user_id)
            if not user.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Usuario con ID {user_id} no encontrado'
                }, status=404)
            
            # Buscar reservas del usuario
            domain = [('partner_id', '=', user_id)]
            booking_records = request.env['hotel.booking'].search(domain)
            
            # Recopilar todos los huéspedes únicos
            guests_data = {}
            
            for booking in booking_records:
                for line in booking.booking_line_ids:
                    for guest in line.guest_info_ids:
                        guest_id = guest.id
                        
                        if guest_id not in guests_data:
                            guests_data[guest_id] = {
                                'guest_id': guest_id,
                                'name': guest.name,
                                'age': guest.age,
                                'gender': guest.gender,
                                'total_bookings': 0,
                                'total_amount': 0,
                                'first_booking': booking.create_date,
                                'last_booking': booking.create_date,
                                'hotels': set(),
                                'statuses': set(),
                            }
                        
                        # Actualizar estadísticas del huésped
                        guests_data[guest_id]['total_bookings'] += 1
                        guests_data[guest_id]['total_amount'] += booking.total_amount
                        guests_data[guest_id]['last_booking'] = max(guests_data[guest_id]['last_booking'], booking.create_date)
                        
                        if booking.hotel_id:
                            guests_data[guest_id]['hotels'].add(booking.hotel_id.name)
                        guests_data[guest_id]['statuses'].add(booking.status_bar)
            
            # Convertir sets a listas y preparar respuesta
            guests_list = []
            for guest_data in guests_data.values():
                guest_data['hotels'] = list(guest_data['hotels'])
                guest_data['statuses'] = list(guest_data['statuses'])
                guests_list.append(guest_data)
            
            # Ordenar por total de reservas (descendente)
            guests_list.sort(key=lambda x: x['total_bookings'], reverse=True)
            
            # Estadísticas generales
            guest_stats = {
                'total_unique_guests': len(guests_list),
                'total_bookings': sum(g['total_bookings'] for g in guests_list),
                'total_amount': sum(g['total_amount'] for g in guests_list),
                'average_bookings_per_guest': sum(g['total_bookings'] for g in guests_list) / len(guests_list) if guests_list else 0,
            }
            
            _logger.info(f"Lista de huéspedes obtenida para usuario {user_id}: {len(guests_list)} huéspedes únicos")
            
            return self._prepare_response({
                'success': True,
                'data': {
                    'user_id': user_id,
                    'user_name': user.name,
                    'guest_stats': guest_stats,
                    'guests': guests_list
                }
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_user_guests: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/user/<int:user_id>/guest/<int:guest_id>/price_info', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_guest_price_info(self, user_id, guest_id, **kw):
        """Obtener información de precios específica de un huésped"""
        try:
            # Verificar que el usuario existe
            user = request.env['res.users'].browse(user_id)
            if not user.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Usuario con ID {user_id} no encontrado'
                }, status=404)
            
            # Verificar que el huésped existe
            guest = request.env['guest.info'].browse(guest_id)
            if not guest.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Huésped con ID {guest_id} no encontrado'
                }, status=404)
            
            # Buscar reservas del usuario que contengan este huésped
            domain = [
                ('partner_id', '=', user_id),
                ('booking_line_ids.guest_info_ids', '=', guest_id)
            ]
            
            # Aplicar filtros adicionales
            if kw.get('status_bar'):
                domain.append(('status_bar', '=', kw.get('status_bar')))
            if kw.get('date_from'):
                domain.append(('check_in', '>=', kw.get('date_from')))
            if kw.get('date_to'):
                domain.append(('check_out', '<=', kw.get('date_to')))
            
            booking_records = request.env['hotel.booking'].search(domain)
            
            # Construir información específica del huésped
            guest_price_info = {
                'guest_id': guest_id,
                'guest_name': guest.name,
                'guest_age': guest.age,
                'guest_gender': guest.gender,
                'total_bookings': len(booking_records),
                'total_amount': sum(booking.total_amount for booking in booking_records),
                'total_discount': sum(booking.discount_amount or 0 for booking in booking_records),
                'bookings': []
            }
            
            for booking in booking_records:
                booking_info = self._build_price_info(booking)
                # Filtrar solo las líneas que contienen este huésped
                guest_lines = []
                for line_info in booking_info['room_prices']:
                    line = request.env['hotel.booking.line'].browse(line_info['line_id'])
                    if guest_id in line.guest_info_ids.ids:
                        guest_lines.append(line_info)
                
                booking_info['guest_specific_lines'] = guest_lines
                guest_price_info['bookings'].append(booking_info)
            
            # Estadísticas adicionales
            if booking_records:
                guest_price_info['average_amount'] = guest_price_info['total_amount'] / guest_price_info['total_bookings']
                guest_price_info['first_booking'] = min(booking.create_date for booking in booking_records)
                guest_price_info['last_booking'] = max(booking.create_date for booking in booking_records)
                guest_price_info['savings_percentage'] = (guest_price_info['total_discount'] / guest_price_info['total_amount'] * 100) if guest_price_info['total_amount'] > 0 else 0
            
            _logger.info(f"Información de precios del huésped {guest_id} obtenida para usuario {user_id}")
            
            return self._prepare_response({
                'success': True,
                'data': guest_price_info
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_guest_price_info: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/guest/<int:guest_id>/price_info', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_guest_direct_price_info(self, guest_id, **kw):
        """Obtener información de precios directamente de un huésped específico"""
        try:
            # Verificar que el huésped existe
            guest = request.env['guest.info'].browse(guest_id)
            if not guest.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Huésped con ID {guest_id} no encontrado'
                }, status=404)
            
            # Buscar reservas que contengan este huésped
            domain = [('booking_line_ids.guest_info_ids', '=', guest_id)]
            
            # Aplicar filtros adicionales
            if kw.get('status_bar'):
                domain.append(('status_bar', '=', kw.get('status_bar')))
            if kw.get('date_from'):
                domain.append(('check_in', '>=', kw.get('date_from')))
            if kw.get('date_to'):
                domain.append(('check_out', '<=', kw.get('date_to')))
            if kw.get('hotel_id'):
                domain.append(('hotel_id', '=', int(kw['hotel_id'])))
            
            booking_records = request.env['hotel.booking'].search(domain)
            
            # Construir información específica del huésped
            guest_price_info = {
                'guest_id': guest_id,
                'guest_name': guest.name,
                'guest_age': guest.age,
                'guest_gender': guest.gender,
                'total_bookings': len(booking_records),
                'total_amount': sum(float(booking.total_amount) for booking in booking_records),
                'total_discount': sum(float(booking.discount_amount or 0) for booking in booking_records),
                'bookings': []
            }
            
            for booking in booking_records:
                booking_info = self._build_price_info(booking)
                # Filtrar solo las líneas que contienen este huésped
                guest_lines = []
                for line_info in booking_info['room_prices']:
                    line = request.env['hotel.booking.line'].browse(line_info['line_id'])
                    if guest_id in line.guest_info_ids.ids:
                        guest_lines.append(line_info)
                
                booking_info['guest_specific_lines'] = guest_lines
                guest_price_info['bookings'].append(booking_info)
            
            # Estadísticas adicionales
            if booking_records:
                guest_price_info['average_amount'] = guest_price_info['total_amount'] / guest_price_info['total_bookings']
                guest_price_info['first_booking'] = min(booking.create_date for booking in booking_records)
                guest_price_info['last_booking'] = max(booking.create_date for booking in booking_records)
                guest_price_info['savings_percentage'] = (guest_price_info['total_discount'] / guest_price_info['total_amount'] * 100) if guest_price_info['total_amount'] > 0 else 0
            
            _logger.info(f"Información de precios del huésped {guest_id} obtenida directamente")
            
            return self._prepare_response({
                'success': True,
                'data': guest_price_info
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_guest_direct_price_info: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/partner/<int:partner_id>/price_info', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_partner_price_info(self, partner_id, **kw):
        """Obtener información de precios de un contacto/empresa específico"""
        try:
            # Verificar que el contacto existe
            partner = request.env['res.partner'].browse(partner_id)
            if not partner.exists():
                return self._prepare_response({
                    'success': False,
                    'error': f'Contacto con ID {partner_id} no encontrado'
                }, status=404)
            
            # Buscar reservas donde este contacto es el partner_id principal
            domain = [('partner_id', '=', partner_id)]
            
            # Aplicar filtros adicionales
            if kw.get('status_bar'):
                domain.append(('status_bar', '=', kw.get('status_bar')))
            if kw.get('date_from'):
                domain.append(('check_in', '>=', kw.get('date_from')))
            if kw.get('date_to'):
                domain.append(('check_out', '<=', kw.get('date_to')))
            if kw.get('hotel_id'):
                domain.append(('hotel_id', '=', int(kw['hotel_id'])))
            
            booking_records = request.env['hotel.booking'].search(domain)
            
            # Construir información específica del contacto
            partner_price_info = {
                'partner_id': partner_id,
                'partner_name': partner.name,
                'partner_type': partner.is_company and 'company' or 'person',
                'partner_email': partner.email,
                'partner_phone': partner.phone,
                'partner_city': partner.city,
                'partner_country': partner.country_id.name if partner.country_id else None,
                'total_bookings': len(booking_records),
                'total_amount': sum(float(booking.total_amount) for booking in booking_records),
                'total_discount': sum(float(booking.discount_amount or 0) for booking in booking_records),
                'bookings': []
            }
            
            for booking in booking_records:
                booking_info = self._build_price_info(booking)
                partner_price_info['bookings'].append(booking_info)
            
            # Estadísticas adicionales
            if booking_records:
                partner_price_info['average_amount'] = partner_price_info['total_amount'] / partner_price_info['total_bookings']
                partner_price_info['first_booking'] = min(booking.create_date for booking in booking_records)
                partner_price_info['last_booking'] = max(booking.create_date for booking in booking_records)
                partner_price_info['savings_percentage'] = (partner_price_info['total_discount'] / partner_price_info['total_amount'] * 100) if partner_price_info['total_amount'] > 0 else 0
                
                # Información de huéspedes únicos
                unique_guests = set()
                for booking in booking_records:
                    for line in booking.booking_line_ids:
                        for guest in line.guest_info_ids:
                            unique_guests.add(guest.id)
                
                partner_price_info['unique_guests_count'] = len(unique_guests)
            
            _logger.info(f"Información de precios del contacto {partner_id} obtenida directamente")
            
            return self._prepare_response({
                'success': True,
                'data': partner_price_info
            })
            
        except Exception as e:
            _logger.exception(f"Error inesperado en get_partner_price_info: {str(e)}")
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)
