# -*- coding: utf-8 -*-
from datetime import datetime, time, date as date_type
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError
from .api_auth import validate_api_key


class ChangeRoomApiController(http.Controller):
    """
    Endpoints para gestionar el cambio de habitación mediante el wizard
    `hotel.booking.line.change.room.wizard`.
    """

    def _get_booking_and_line(self, booking_id, line_id=None):
        booking = request.env['hotel.booking'].browse(booking_id)
        if not booking.exists():
            raise UserError('La reserva solicitada no existe.')

        line = None
        if line_id:
            line = booking.booking_line_ids.filtered(lambda booking_line: booking_line.id == line_id)
            if not line:
                raise UserError('La línea de reserva indicada no pertenece a la reserva.')
        else:
            if len(booking.booking_line_ids) == 1:
                line = booking.booking_line_ids
            else:
                raise UserError('Debe especificar booking_line_id cuando la reserva tiene múltiples líneas.')
        return booking, line

    def _parse_datetime_or_date(self, date_str, field_name='fecha'):
        """Parsear string a datetime o date con manejo de errores"""
        if not date_str:
            return None
        
        try:
            if isinstance(date_str, str):
                # Intentar parsear como datetime primero (con hora)
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                    try:
                        return datetime.strptime(date_str.replace('T', ' ').split('.')[0], fmt)
                    except ValueError:
                        continue
                # Si no funciona, intentar como fecha
                for fmt in ['%Y-%m-%d']:
                    try:
                        return datetime.strptime(date_str, fmt).date()
                    except ValueError:
                        continue
                raise ValueError(f'Formato de {field_name} no reconocido: {date_str}')
            return date_str
        except Exception as e:
            raise ValueError(f'Error al procesar {field_name}: {str(e)}')

    @http.route(
        '/api/hotel/reserva/<int:booking_id>/change_room/options',
        type='json',
        auth='public',
        methods=['GET', 'POST'],
        csrf=False,
        website=False,
    )
    @validate_api_key
    def get_change_room_options(self, booking_id, **kwargs):
        """
        Obtener valores predeterminados y habitaciones disponibles para el cambio.
        """
        payload = request.get_json_data() or {}
        line_id = payload.get('booking_line_id') or kwargs.get('booking_line_id')
        booking, line = self._get_booking_and_line(booking_id, int(line_id) if line_id else None)

        proposed_start = fields.Date.context_today(request.env.user)
        proposed_end = booking.check_out.date() if hasattr(booking.check_out, 'date') else booking.check_out

        wizard_ctx = {
            'default_booking_id': booking.id,
            'default_booking_line_id': line.id,
        }
        wizard = request.env['hotel.booking.line.change.room.wizard'].with_context(wizard_ctx).new({})

        room_ids = wizard.available_rooms.ids if wizard.available_rooms else []
        rooms = request.env['product.product'].browse(room_ids)
        available_room_payload = [
            {
                'id': room.id,
                'name': room.display_name,
                'code': room.default_code or '',
                'price': room.list_price,
            }
            for room in rooms
        ]

        defaults = {
            'booking_id': booking.id,
            'booking_line_id': line.id,
            'booking_line_name': line.display_name,
            'current_room_id': line.product_id.id,
            'current_room_name': line.product_id.display_name,
            'current_room_code': line.product_id.default_code or '',
            'current_room_capacity': {
                'max_adult': line.product_id.product_tmpl_id.max_adult if hasattr(line.product_id.product_tmpl_id, 'max_adult') else None,
                'max_child': line.product_id.product_tmpl_id.max_child if hasattr(line.product_id.product_tmpl_id, 'max_child') else None,
            },
            'current_room_price': line.price,
            'current_room_discount': line.discount,
            'current_room_subtotal': line.subtotal_price,
            'current_room_total': line.taxed_price,
            'current_room_currency': {
                'id': booking.currency_id.id if booking.currency_id else None,
                'name': booking.currency_id.name if booking.currency_id else None,
                'symbol': booking.currency_id.symbol if booking.currency_id else None,
            },
            'change_start_date': wizard.change_start_date or proposed_start,
            'change_end_date': wizard.change_end_date or proposed_end,
            'total_nights': wizard.total_nights,
            'estimated_total': wizard.estimated_total,
            'use_custom_price': wizard.use_custom_price,
            'custom_price': wizard.custom_price,
        }

        return {
            'success': True,
            'data': {
                'defaults': defaults,
                'available_rooms': available_room_payload,
            }
        }

    @http.route(
        '/api/hotel/reserva/<int:booking_id>/change_room',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
        website=False,
    )
    @validate_api_key
    def apply_change_room(self, booking_id):
        """
        Ejecutar el cambio de habitación con los parámetros enviados desde el frontend.
        
        Acepta fechas con o sin horas:
        - change_start_date: "2024-01-15" o "2024-01-15 14:00:00"
        - change_end_date: "2024-01-20" o "2024-01-20 11:00:00"
        
        O también puede recibir:
        - change_start_datetime: "2024-01-15T14:00:00" (ISO datetime)
        - change_end_datetime: "2024-01-20T11:00:00" (ISO datetime)
        
        Si se proporcionan horas, se usarán. Si no, se usarán las horas de la reserva original.
        """
        payload = request.get_json_data() or {}
        line_id = payload.get('booking_line_id')
        booking, line = self._get_booking_and_line(booking_id, line_id)

        new_room_id = payload.get('new_room_id')
        if not new_room_id:
            raise UserError('Debe proporcionar new_room_id.')

        # Aceptar fechas con o sin horas
        # Prioridad: horas separadas > change_start_datetime > change_start_date
        # También aceptar horas separadas directamente (check_in_hour, check_in_minute, etc.)
        start_datetime_str = payload.get('change_start_datetime') or payload.get('change_start_date')
        end_datetime_str = payload.get('change_end_datetime') or payload.get('change_end_date')
        
        # Verificar si se proporcionaron horas separadas
        check_in_hour = payload.get('check_in_hour')
        check_in_minute = payload.get('check_in_minute')
        check_out_hour = payload.get('check_out_hour')
        check_out_minute = payload.get('check_out_minute')
        
        # Si se proporcionaron horas separadas, construir datetime desde fecha + horas
        if start_datetime_str and check_in_hour is not None:
            # Construir datetime desde fecha + horas separadas
            start_date_obj = self._parse_datetime_or_date(start_datetime_str, 'change_start')
            if isinstance(start_date_obj, datetime):
                start_date_obj = start_date_obj.date()
            elif not hasattr(start_date_obj, 'year'):  # No es date ni datetime
                if isinstance(start_datetime_str, str):
                    start_date_obj = fields.Date.from_string(start_datetime_str)
                else:
                    raise UserError('No se pudo parsear la fecha de inicio.')
            
            # Validar que tenemos un objeto date válido antes de usar datetime.combine
            if not isinstance(start_date_obj, date_type):
                raise UserError('Fecha de inicio inválida.')
            
            # Crear datetime con las horas proporcionadas
            # start_date_obj está garantizado como date_type por la validación anterior
            start_datetime = datetime.combine(
                start_date_obj,  # type: ignore[arg-type]
                time(
                    hour=int(check_in_hour),
                    minute=int(check_in_minute) if check_in_minute is not None else 0
                )
            )
            start_datetime_str = start_datetime.strftime('%Y-%m-%d %H:%M:%S')
        
        if end_datetime_str and check_out_hour is not None:
            # Construir datetime desde fecha + horas separadas
            end_date_obj = self._parse_datetime_or_date(end_datetime_str, 'change_end')
            if isinstance(end_date_obj, datetime):
                end_date_obj = end_date_obj.date()
            elif not hasattr(end_date_obj, 'year'):  # No es date ni datetime
                if isinstance(end_datetime_str, str):
                    end_date_obj = fields.Date.from_string(end_datetime_str)
                else:
                    raise UserError('No se pudo parsear la fecha de fin.')
            
            # Validar que tenemos un objeto date válido antes de usar datetime.combine
            if not isinstance(end_date_obj, date_type):
                raise UserError('Fecha de fin inválida.')
            
            # Crear datetime con las horas proporcionadas
            # end_date_obj está garantizado como date_type por la validación anterior
            end_datetime = datetime.combine(
                end_date_obj,  # type: ignore[arg-type]
                time(
                    hour=int(check_out_hour),
                    minute=int(check_out_minute) if check_out_minute is not None else 0
                )
            )
            end_datetime_str = end_datetime.strftime('%Y-%m-%d %H:%M:%S')
        
        if not start_datetime_str or not end_datetime_str:
            raise UserError('Debe proporcionar change_start_date/change_start_datetime y change_end_date/change_end_datetime, o fechas con check_in_hour/check_out_hour.')

        # Parsear fechas/horas
        start_datetime = self._parse_datetime_or_date(start_datetime_str, 'change_start')
        end_datetime = self._parse_datetime_or_date(end_datetime_str, 'change_end')
        
        # Extraer fecha y hora si es datetime, o solo fecha si es date
        if isinstance(start_datetime, datetime):
            change_start_date = start_datetime.date()
            change_start_hour = start_datetime.hour
            change_start_minute = start_datetime.minute
        else:
            change_start_date = start_datetime
            # Si no hay hora en datetime pero se proporcionaron horas separadas, usarlas
            if check_in_hour is not None:
                change_start_hour = int(check_in_hour)
                change_start_minute = int(check_in_minute) if check_in_minute is not None else 0
            else:
                change_start_hour = None
                change_start_minute = None
        
        if isinstance(end_datetime, datetime):
            change_end_date = end_datetime.date()
            change_end_hour = end_datetime.hour
            change_end_minute = end_datetime.minute
        else:
            change_end_date = end_datetime
            # Si no hay hora en datetime pero se proporcionaron horas separadas, usarlas
            if check_out_hour is not None:
                change_end_hour = int(check_out_hour)
                change_end_minute = int(check_out_minute) if check_out_minute is not None else 0
            else:
                change_end_hour = None
                change_end_minute = None

        use_custom_price = bool(payload.get('use_custom_price'))
        custom_price = payload.get('custom_price') if use_custom_price else False

        wizard_ctx = {
            'default_booking_id': booking.id,
            'default_booking_line_id': line.id,
            # Pasar horas al contexto para que el wizard las use
            'change_start_hour': change_start_hour,
            'change_start_minute': change_start_minute,
            'change_end_hour': change_end_hour,
            'change_end_minute': change_end_minute,
        }
        wizard_vals = {
            'booking_id': booking.id,
            'booking_line_id': line.id,
            'current_room_id': line.product_id.id,
            'new_room_id': int(new_room_id),
            'change_start_date': change_start_date,
            'change_end_date': change_end_date,
            'use_custom_price': use_custom_price,
            'custom_price': custom_price,
            'note': payload.get('note'),
        }

        wizard = request.env['hotel.booking.line.change.room.wizard'].with_context(wizard_ctx).create(wizard_vals)
        try:
            action_result = wizard.action_confirm()
        except Exception as exc:
            raise UserError(f'No se pudo aplicar el cambio de habitación: {exc}') from exc

        # Nota: No es necesario invalidate_recordset() aquí. Odoo manejará automáticamente
        # el flush de los cambios al final de la transacción. Las llamadas a invalidate_recordset()
        # pueden causar errores de serialización en PostgreSQL cuando hay transacciones concurrentes.
        # Los datos se actualizarán automáticamente cuando se acceda a ellos.
        
        # Obtener la nueva reserva creada (si existe en action_result)
        new_booking_id = None
        if isinstance(action_result, dict) and action_result.get('res_model') == 'hotel.booking':
            if action_result.get('res_id'):
                new_booking_id = action_result['res_id']
            elif action_result.get('domain'):
                # Intentar obtener el ID desde el dominio si está disponible
                domain = action_result.get('domain', [])
                for term in domain:
                    if isinstance(term, (list, tuple)) and len(term) == 3 and term[0] == 'id':
                        if term[1] == 'in' and isinstance(term[2], list) and term[2]:
                            new_booking_id = term[2][0]
                            break
        
        # Si no se encontró en action_result, buscar la reserva más reciente conectada
        if not new_booking_id:
            connected_booking = booking.connected_booking_id
            if connected_booking:
                new_booking_id = connected_booking.id
        
        # Construir respuesta con información de la nueva reserva
        response_data = {
            'reserva_id': booking.id,
            'action': action_result,
        }
        
        # Si se encontró la nueva reserva, incluir sus datos con horas
        if new_booking_id:
            new_booking = request.env['hotel.booking'].browse(new_booking_id)
            if new_booking.exists():
                # Incluir información básica de la nueva reserva con horas
                check_in_hour = None
                check_in_minute = None
                check_out_hour = None
                check_out_minute = None
                
                if new_booking.check_in and isinstance(new_booking.check_in, datetime):
                    check_in_hour = new_booking.check_in.hour
                    check_in_minute = new_booking.check_in.minute
                
                if new_booking.check_out and isinstance(new_booking.check_out, datetime):
                    check_out_hour = new_booking.check_out.hour
                    check_out_minute = new_booking.check_out.minute
                
                response_data['new_reserva'] = {
                    'id': new_booking.id,
                    'sequence_id': new_booking.sequence_id,
                    'check_in': new_booking.check_in,
                    'check_out': new_booking.check_out,
                    'check_in_hour': check_in_hour,
                    'check_in_minute': check_in_minute,
                    'check_out_hour': check_out_hour,
                    'check_out_minute': check_out_minute,
                    'status_bar': new_booking.status_bar,
                }

        return {
            'success': True,
            'message': 'Cambio de habitación aplicado correctamente.',
            'data': response_data
        }


