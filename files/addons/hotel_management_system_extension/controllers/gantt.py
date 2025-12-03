from datetime import date, datetime, timedelta
import logging
from odoo import http, _, fields
from odoo.http import request, Response
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)

class ReservationGanttController(http.Controller):

    @http.route('/hotel/gantt_data', type='json', auth='user')
    def get_gantt_data(self, **kwargs):

        try:
            _logger.info("=== INICIANDO get_gantt_data ===")
            _logger.info(f"kwargs: {kwargs}")
            
            target_date_str = kwargs.get('target_date')
            target_date = date.fromisoformat(target_date_str) if target_date_str else date.today()
            
            _logger.info(f"target_date: {target_date}")
            
            first_day = target_date.replace(day=1)
            last_day = first_day + timedelta(days=31) # Cargar un poco más para evitar recargas constantes
            
            _logger.info(f"first_day: {first_day}, last_day: {last_day}")
            
            # Obtener hotel_id del request si está presente
            hotel_id = kwargs.get('hotel_id')
            _logger.info(f"hotel_id recibido: {hotel_id}")
            
            # Obtener datos de habitaciones y reservas
            rooms = self._get_rooms(hotel_id)
            _logger.info(f"rooms obtenidas: {len(rooms)}")
            
            reservations = self._get_reservations(first_day, last_day)
            _logger.info(f"reservations obtenidas: {len(reservations)}")
            
            # Construir la información del mes que el JS avanzado necesita
            month_info = self._build_month_info(target_date)
            _logger.info(f"month_info: {month_info}")
            
            result = {
                'rooms': rooms,
                'reservations': reservations,
                'month_info': month_info,
                'success': True
            }
            
            _logger.info(f"Resultado final: {result}")
            return result
        except Exception as e:
            _logger.error(f"Error en get_gantt_data: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _get_or_create_default_partner(self):
        """
        Obtiene o crea un cliente por defecto para reservas rápidas.
        """
        try:
            # Buscar cliente por defecto existente
            default_partner = request.env['res.partner'].sudo().search([
                ('name', '=', 'Cliente de Paso'),
                ('is_company', '=', False)
            ], limit=1)
            
            if not default_partner:
                # Crear cliente por defecto
                default_partner = request.env['res.partner'].sudo().create({
                    'name': 'Cliente de Paso',
                    'is_company': False,
                    'email': 'cliente.paso@hotel.com',
                    'phone': '+51 999 999 999',
                    'street': 'Dirección Temporal',
                    'city': 'Ciudad',
                    'country_id': request.env['res.country'].sudo().search([('code', '=', 'PE')], limit=1).id,
                })
            
            return default_partner.id
        except Exception as e:
            _logger.error(f"Error creando cliente por defecto: {str(e)}")
            return False

    @http.route('/hotel/get_hotels', type='json', auth='user')
    def get_hotels(self, **kwargs):
        """
        Proporciona la lista de hoteles disponibles para el filtro.
        """
        try:
            # Verificar si el modelo existe
            try:
                hotel_model = request.env['hotel.hotels'].sudo()
            except Exception as model_error:
                # Devolver hoteles de prueba si el modelo no existe
                test_hotels = [
                    {'id': 1, 'name': 'Hotel Central'},
                    {'id': 2, 'name': 'Hotel Plaza'},
                    {'id': 3, 'name': 'Hotel Resort'},
                ]
                return {
                    'success': True,
                    'hotels': test_hotels
                }
            
            # Obtener todos los hoteles activos
            hotels = hotel_model.search_read(
                [('active', '=', True)],
                fields=['id', 'name'],
                order='name'
            )
            
            # Si no hay hoteles, crear algunos de prueba
            if not hotels:
                self._create_test_hotels()
                # Recargar los hoteles
                hotels = hotel_model.search_read(
                    [('active', '=', True)],
                    fields=['id', 'name'],
                    order='name'
                )
            
            return {
                'success': True,
                'hotels': hotels
            }
        except Exception as e:
            _logger.error(f"Error en get_hotels: {str(e)}")
            return {'success': False, 'error': str(e)}

    @http.route('/hotel/get_default_partner', type='json', auth='user')
    def get_default_partner(self, **kwargs):
        """
        Obtiene el ID del cliente por defecto para reservas rápidas.
        """
        try:
            default_partner_id = self._get_or_create_default_partner()
            return {
                'success': True,
                'default_partner_id': default_partner_id
            }
        except Exception as e:
            _logger.error(f"Error obteniendo cliente por defecto: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/hotel/reuse_room_ready_booking', type='json', auth='user')
    def reuse_room_ready_booking(self, **kwargs):
        """
        Reutiliza una reserva en estado 'room_ready' para una nueva reserva.
        """
        try:
            booking_id = kwargs.get('booking_id')
            if not booking_id:
                return {
                    'success': False,
                    'error': 'ID de reserva no proporcionado'
                }
            
            # Buscar la reserva
            booking = request.env['hotel.booking'].sudo().browse(booking_id)
            if not booking.exists():
                return {
                    'success': False,
                    'error': 'Reserva no encontrada'
                }
            
            # Verificar que esté en estado 'room_ready'
            if booking.status_bar != 'room_ready':
                return {
                    'success': False,
                    'error': 'La reserva no está en estado "Habitación Lista"'
                }
            
            # Llamar al método para crear nueva reserva
            new_booking = booking.action_reuse_room_ready_booking()
            
            return {
                'success': True,
                'message': 'Nueva reserva creada exitosamente',
                'new_booking_id': new_booking.id
            }
            
        except Exception as e:
            _logger.error(f"Error reutilizando reserva: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


    def _get_rooms(self, hotel_id=None):
        """Obtiene las habitaciones (product.template) que son de tipo habitación."""
        try:
            domain = [('is_room_type', '=', True)]
            
            # Validar y aplicar filtro de hotel
            if hotel_id and hotel_id != 'null' and hotel_id != '' and hotel_id != 'undefined' and hotel_id is not None and hotel_id != 'None':
                try:
                    hotel_id_int = int(hotel_id)
                    domain.append(('hotel_id', '=', hotel_id_int))
                except (ValueError, TypeError):
                    pass
            
            # Si no hay habitaciones, crear algunas de prueba
            all_room_types = request.env['product.template'].sudo().search_count([('is_room_type', '=', True)])
            if all_room_types == 0:
                self._create_test_rooms()
            
            # Obtener habitaciones
            rooms = request.env['product.template'].sudo().search_read(
                domain,
                fields=['id', 'name', 'list_price', 'max_adult', 'max_child', 'hotel_id'],
                order='name',
                limit=1000
            )
            
            # Agregar campos adicionales necesarios para el panel
            for room in rooms:
                # Obtener el tipo de habitación (categoría) - usar una categoría por defecto
                room['room_type_id'] = False
                
                # Calcular capacidad total (adultos + niños)
                max_adult = room.get('max_adult', 1)
                max_child = room.get('max_child', 0)
                room['capacity'] = max_adult + max_child
                
                # Establecer precio por defecto si no existe
                if not room.get('list_price'):
                    room['price'] = 0.0
                else:
                    room['price'] = room['list_price']
                
                # Procesar hotel_id para asegurar formato correcto
                original_hotel_id = room.get('hotel_id')
                if original_hotel_id:
                    if isinstance(original_hotel_id, (list, tuple)) and len(original_hotel_id) >= 2:
                        # Convertir tupla a lista si es necesario
                        if isinstance(original_hotel_id, tuple):
                            room['hotel_id'] = list(original_hotel_id)
                        else:
                            room['hotel_id'] = original_hotel_id
                    elif isinstance(original_hotel_id, (int, str)):
                        try:
                            hotel_id_int = int(original_hotel_id)
                            hotel = request.env['hotel.hotels'].sudo().browse(hotel_id_int)
                            if hotel.exists():
                                room['hotel_id'] = [hotel_id_int, hotel.name]
                            else:
                                room['hotel_id'] = False
                        except (ValueError, TypeError):
                            room['hotel_id'] = False
                    else:
                        room['hotel_id'] = False
                else:
                    room['hotel_id'] = False
                
                # Calcular el estado de la habitación basado en las reservas actuales
                room_status = self._calculate_room_status(room['id'])
                room['status'] = room_status
            
            return rooms
        except Exception as e:
            _logger.error("Error al obtener habitaciones: %s", str(e))
            return []
    
    def _create_test_hotels(self):
        """Crea hoteles de prueba para el dashboard."""
        try:
            # Crear algunos hoteles de prueba
            test_hotels = [
                {
                    'name': 'Hotel Central',
                    'active': True,
                },
                {
                    'name': 'Hotel Plaza',
                    'active': True,
                },
                {
                    'name': 'Hotel Resort',
                    'active': True,
                },
            ]
            
            for hotel_data in test_hotels:
                # Verificar si el hotel ya existe
                existing = request.env['hotel.hotels'].sudo().search([
                    ('name', '=', hotel_data['name']),
                    ('active', '=', True)
                ], limit=1)
                
                if not existing:
                    request.env['hotel.hotels'].sudo().create(hotel_data)
                    _logger.info(f"Hotel de prueba creado: {hotel_data['name']}")
                else:
                    _logger.info(f"Hotel ya existe: {hotel_data['name']}")
                    
        except Exception as e:
            _logger.error(f"Error creando hoteles de prueba: {str(e)}")

    def _create_test_rooms(self):
        """Crea habitaciones de prueba para el dashboard."""
        try:
            # Primero obtener o crear hoteles de prueba
            hotel_central = request.env['hotel.hotels'].sudo().search([('name', '=', 'Hotel Central')], limit=1)
            hotel_plaza = request.env['hotel.hotels'].sudo().search([('name', '=', 'Hotel Plaza')], limit=1)
            hotel_resort = request.env['hotel.hotels'].sudo().search([('name', '=', 'Hotel Resort')], limit=1)
            
            # Crear hoteles si no existen
            if not hotel_central:
                hotel_central = request.env['hotel.hotels'].sudo().create({'name': 'Hotel Central', 'active': True})
            if not hotel_plaza:
                hotel_plaza = request.env['hotel.hotels'].sudo().create({'name': 'Hotel Plaza', 'active': True})
            if not hotel_resort:
                hotel_resort = request.env['hotel.hotels'].sudo().create({'name': 'Hotel Resort', 'active': True})
            
            # Crear habitaciones de prueba con hoteles asignados
            test_rooms = [
                {
                    'name': 'Habitación 101',
                    'is_room_type': True,
                    'hotel_id': hotel_central.id,
                    'list_price': 100.0,
                    'max_adult': 2,
                    'max_child': 1,
                },
                {
                    'name': 'Habitación 102',
                    'is_room_type': True,
                    'hotel_id': hotel_central.id,
                    'list_price': 120.0,
                    'max_adult': 2,
                    'max_child': 2,
                },
                {
                    'name': 'Habitación 201',
                    'is_room_type': True,
                    'hotel_id': hotel_plaza.id,
                    'list_price': 150.0,
                    'max_adult': 3,
                    'max_child': 1,
                },
                {
                    'name': 'Habitación 301',
                    'is_room_type': True,
                    'hotel_id': hotel_resort.id,
                    'list_price': 200.0,
                    'max_adult': 4,
                    'max_child': 2,
                },
            ]
            
            for room_data in test_rooms:
                # Verificar si la habitación ya existe
                existing = request.env['product.template'].sudo().search([
                    ('name', '=', room_data['name']),
                    ('is_room_type', '=', True)
                ], limit=1)
                
                if not existing:
                    request.env['product.template'].sudo().create(room_data)
                    _logger.info(f"Habitación de prueba creada: {room_data['name']} para hotel {room_data['hotel_id']}")
                else:
                    _logger.info(f"Habitación ya existe: {room_data['name']}")
                    
        except Exception as e:
            _logger.error(f"Error creando habitaciones de prueba: {str(e)}")

    def _assign_default_hotels_to_rooms(self):
        """Asigna hoteles por defecto a habitaciones que no tienen hotel asignado."""
        try:
            _logger.info("=== INICIANDO _assign_default_hotels_to_rooms ===")
            
            # Obtener el primer hotel disponible
            default_hotel = request.env['hotel.hotels'].sudo().search([('active', '=', True)], limit=1)
            
            if not default_hotel:
                _logger.warning("No hay hoteles disponibles para asignar por defecto")
                return
            
            _logger.info(f"Hotel por defecto encontrado: {default_hotel.name} (ID: {default_hotel.id})")
            
            # Obtener habitaciones sin hotel asignado
            rooms_without_hotel = request.env['product.template'].sudo().search([
                ('is_room_type', '=', True),
                ('hotel_id', '=', False)
            ])
            
            _logger.info(f"Habitaciones sin hotel asignado encontradas: {len(rooms_without_hotel)}")
            
            if rooms_without_hotel:
                # Asignar el hotel por defecto a todas las habitaciones sin hotel
                rooms_without_hotel.write({'hotel_id': default_hotel.id})
                _logger.info(f"Asignado hotel '{default_hotel.name}' a {len(rooms_without_hotel)} habitaciones")
                
                # Verificar que se asignaron correctamente
                for room in rooms_without_hotel:
                    _logger.info(f"Habitación '{room.name}' ahora tiene hotel_id: {room.hotel_id}")
            else:
                _logger.info("No hay habitaciones sin hotel asignado - las habitaciones ya tienen hoteles asignados")
                
            _logger.info("=== FINALIZANDO _assign_default_hotels_to_rooms ===")
                
        except Exception as e:
            _logger.error(f"Error asignando hoteles por defecto: {str(e)}")

    def _calculate_room_status(self, room_id):
        """
        Calcula el estado actual de una habitación basado en las reservas.
        Considera que las habitaciones en estado 'room_ready' están disponibles inmediatamente.
        """
        try:
            today = datetime.now().date()
            
            # Buscar reservas activas para esta habitación (excluyendo 'room_ready')
            active_bookings = request.env['hotel.booking.line'].sudo().search([
                ('product_tmpl_id', '=', room_id),
                ('check_in', '<=', datetime.combine(today, datetime.min.time())),
                ('check_out', '>=', datetime.combine(today, datetime.min.time())),
                ('booking_id.status_bar', 'not in', ['cancel', 'cancelled', 'room_ready'])
            ])
            
            if active_bookings:
                # Si hay reservas activas (excluyendo room_ready), la habitación está ocupada
                return 'occupied'
            else:
                # Verificar si hay reservas en estado 'room_ready' para hoy
                room_ready_bookings = request.env['hotel.booking.line'].sudo().search([
                    ('product_tmpl_id', '=', room_id),
                    ('check_in', '<=', datetime.combine(today, datetime.min.time())),
                    ('check_out', '>=', datetime.combine(today, datetime.min.time())),
                    ('booking_id.status_bar', '=', 'room_ready')
                ])
                
                if room_ready_bookings:
                    # Si hay reservas en 'room_ready', la habitación está disponible inmediatamente
                    # pero marcamos que tiene una reserva reutilizable
                    return 'available_reusable'
                
                # Si no hay reservas activas ni room_ready, verificar reservas futuras
                future_bookings = request.env['hotel.booking.line'].sudo().search([
                    ('product_tmpl_id', '=', room_id),
                    ('check_in', '>', datetime.combine(today, datetime.min.time())),
                    ('booking_id.status_bar', 'not in', ['cancel', 'cancelled', 'room_ready'])
                ])
                
                if future_bookings:
                    # Si hay reservas futuras, la habitación está reservada
                    return 'reserved'
                else:
                    # Si no hay reservas, la habitación está disponible
                    return 'available'
                    
        except Exception as e:
            _logger.error("Error al calcular estado de habitación %s: %s", room_id, str(e))
            return 'available'
            
    @http.route('/hotel/gantt_room_panel_data', type='json', auth='user')
    def get_room_panel_data(self, **kwargs):
        """
        Proporciona los datos necesarios para el panel de habitaciones.
        """
        try:
            _logger.info("=== INICIANDO get_room_panel_data ===")
            _logger.info(f"kwargs: {kwargs}")
            
            hotel_id = kwargs.get('hotel_id')
            _logger.info(f"hotel_id: {hotel_id}")
            
            # Obtener habitaciones con sus estados actuales
            rooms = self._get_rooms(hotel_id)
            _logger.info(f"Habitaciones obtenidas: {len(rooms)}")
            
            # Contar habitaciones por estado
            status_counts = {
                'all': len(rooms),
                'available': 0,
                'occupied': 0,
                'reserved': 0,
                'cleaning': 0,
                'maintenance': 0
            }
            
            for room in rooms:
                status = room.get('status', 'available')
                if status == 'available':
                    status_counts['available'] += 1
                elif status == 'occupied':
                    status_counts['occupied'] += 1
                elif status in ['draft', 'confirm', 'reserved']:
                    status_counts['reserved'] += 1
                elif status == 'cleaning':
                    status_counts['cleaning'] += 1
                elif status == 'maintenance':
                    status_counts['maintenance'] += 1
            
            _logger.info(f"Status counts: {status_counts}")
            
            result = {
                'success': True,
                'rooms': rooms,
                'status_counts': status_counts
            }
            
            _logger.info("get_room_panel_data completado exitosamente")
            return result
            
        except Exception as e:
            _logger.error("Error en get_room_panel_data: %s", str(e))
            import traceback
            _logger.error("Traceback: %s", traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }

    @http.route('/hotel/gantt_filters', type='json', auth='user')
    def get_room_panel_filters(self, **kwargs):
        """
        Proporciona los datos para los filtros del panel de habitaciones.
        """
        try:
            _logger.info("=== INICIANDO get_room_panel_filters ===")
            
            # Obtener hoteles únicos - usar modelo correcto
            hotels = request.env['hotel.hotels'].sudo().search_read(
                [('active', '=', True)],
                fields=['id', 'name'],
                order='name'
            )
            _logger.info(f"Hoteles obtenidos: {len(hotels)}")
            
            # Obtener tipos de habitación únicos - usar categorías de productos
            room_types = request.env['product.category'].sudo().search_read(
                [],  # Obtener todas las categorías por ahora
                fields=['id', 'name'],
                order='name'
            )
            _logger.info(f"Tipos de habitación obtenidos: {len(room_types)}")
            
            # Estados disponibles
            statuses = [
                {'key': 'available', 'label': 'Disponible'},
                {'key': 'occupied', 'label': 'Ocupada'},
                {'key': 'reserved', 'label': 'Reservada'},
                {'key': 'maintenance', 'label': 'Mantenimiento'},
                {'key': 'cleaning', 'label': 'Limpieza'}
            ]
            
            result = {
                'success': True,
                'hotels': hotels,
                'room_types': room_types,
                'statuses': statuses
            }
            
            _logger.info("get_room_panel_filters completado exitosamente")
            return result
            
        except Exception as e:
            _logger.error("Error en get_room_panel_filters: %s", str(e))
            import traceback
            _logger.error("Traceback: %s", traceback.format_exc())
            return {
                'success': False,
                'error': str(e)
            }

    def _get_reservations(self, start_date, end_date):
        """Obtiene las reservas que se cruzan con el rango de fechas."""
        try:
            domain = [
                ('check_in', '<=', datetime.combine(end_date, datetime.max.time())),
                ('check_out', '>=', datetime.combine(start_date, datetime.min.time())),
                ('status_bar', 'not in', ['cancel', 'cancelled', 'room_ready']),  # Excluir también room_ready
            ]
            
            # Usar search_read para mejor rendimiento
            bookings = request.env['hotel.booking'].sudo().search_read(
                domain,
                fields=['id', 'check_in', 'check_out', 'status_bar', 'partner_id', 'total_amount', 'currency_id', 
                       'connected_booking_id', 'is_room_change_origin', 'is_room_change_destination'],
                limit=1000  # Prevención contra consultas demasiado grandes
            )
            
            # Debug: Verificar que los campos se están enviando
            print("=== DEBUG: Campos de reservas ===")
            for booking in bookings:
                if booking.get('connected_booking_id') or booking.get('is_room_change_origin') or booking.get('is_room_change_destination'):
                    print(f"🔗 Reserva {booking['id']}: connected_booking_id={booking.get('connected_booking_id')}, is_room_change_origin={booking.get('is_room_change_origin')}, is_room_change_destination={booking.get('is_room_change_destination')}")
                    print(f"   Fechas: {booking.get('check_in')} - {booking.get('check_out')}, Estado: {booking.get('status_bar')}")
            
            # Obtener los IDs de las reservas
            booking_ids = [b['id'] for b in bookings]
            
            # Obtener las líneas de reserva en una sola consulta
            booking_lines = request.env['hotel.booking.line'].sudo().search_read(
                [('booking_id', 'in', booking_ids)],
                fields=['id', 'booking_id', 'product_tmpl_id', 'booking_days', 'discount_reason']
            )
            
            # Crear un diccionario de líneas por booking_id
            lines_by_booking = {}
            for line in booking_lines:
                if line.get('booking_id'):
                    booking_id = line['booking_id'][0]
                    if booking_id not in lines_by_booking:
                        lines_by_booking[booking_id] = []
                    lines_by_booking[booking_id].append(line)
            
            # Construir la respuesta con fechas específicas por línea
            reservations = []
            for booking in bookings:
                booking_id = booking.get('id')
                if booking_id and booking_id in lines_by_booking:
                    # Obtener fechas base del booking
                    booking_check_in = booking.get('check_in')
                    booking_check_out = booking.get('check_out')
                    
                    if not booking_check_in or not booking_check_out:
                        continue
                        
                    # Convertir a timezone local
                    try:
                        check_in_base = fields.Datetime.context_timestamp(request.env.user, booking_check_in)
                        check_out_base = fields.Datetime.context_timestamp(request.env.user, booking_check_out)
                    except:
                        check_in_base = booking_check_in
                        check_out_base = booking_check_out
                    
                    # Ordenar líneas por ID para procesarlas secuencialmente
                    lines = sorted(lines_by_booking[booking_id], key=lambda x: x.get('id', 0))
                    
                    # Calcular fechas específicas para cada línea basándose en booking_days
                    current_date = check_in_base
                    
                    _logger.info(f"Procesando booking {booking_id} con {len(lines)} líneas")
                    
                    # Detectar si hay segmentos de cambio de habitación
                    has_room_changes = len(lines) > 1 and any(
                        line.get('product_tmpl_id') != lines[0].get('product_tmpl_id') 
                        for line in lines[1:] 
                        if line.get('product_tmpl_id')
                    )
                    
                    if has_room_changes:
                        # CÓDIGO ESPECÍFICO PARA CAMBIOS DE HABITACIÓN
                        _logger.info(f"Procesando booking {booking_id} como CAMBIO DE HABITACIÓN con {len(lines)} líneas")
                        
                        for i, line in enumerate(lines):
                            if line.get('product_tmpl_id'):
                                booking_days = line.get('booking_days', 0)
                                _logger.info(f"CAMBIO - Línea {line.get('id')}: booking_days={booking_days}, product={line.get('product_tmpl_id')}")
                                
                                # Si booking_days es 0, saltar esta línea
                                if booking_days <= 0:
                                    _logger.info(f"CAMBIO - Saltando línea {line.get('id')} porque booking_days={booking_days}")
                                    continue
                                    
                                if i == 0:
                                    # Primera línea: segmento original
                                    line_start = check_in_base
                                    # Usar booking_days directamente (puede ser fraccional para reservas de pocas horas)
                                    line_end = check_in_base + timedelta(days=booking_days)
                                else:
                                    # Líneas siguientes: segmentos de cambio
                                    # Calcular fecha de inicio basándose en la fecha de cambio
                                    change_start = check_in_base + timedelta(days=sum(lines[j].get('booking_days', 0) for j in range(i)))
                                    line_start = change_start
                                    # Usar booking_days directamente (puede ser fraccional)
                                    line_end = change_start + timedelta(days=booking_days)
                                
                                _logger.info(f"CAMBIO - Línea {line.get('id')}: {line_start} -> {line_end} ({booking_days} días)")
                                
                                # Procesar reserva para cambio de habitación
                                self._process_room_change_reservation(reservations, line, booking, line_start, line_end, booking_id)
                    else:
                        # CÓDIGO ESPECÍFICO PARA NUEVAS RESERVAS
                        _logger.info(f"Procesando booking {booking_id} como NUEVA RESERVA con {len(lines)} líneas")
                        
                        for i, line in enumerate(lines):
                            if line.get('product_tmpl_id'):
                                booking_days = line.get('booking_days', 0)
                                _logger.info(f"NUEVA - Línea {line.get('id')}: booking_days={booking_days}, product={line.get('product_tmpl_id')}")
                                
                                # Si booking_days es 0, saltar esta línea
                                if booking_days <= 0:
                                    _logger.info(f"NUEVA - Saltando línea {line.get('id')} porque booking_days={booking_days}")
                                    continue
                                    
                                # Calcular fechas específicas para esta línea (checkout exclusivo para reservas regulares)
                                line_start = current_date
                                line_end = current_date + timedelta(days=booking_days)
                                
                                _logger.info(f"NUEVA - Línea {line.get('id')}: {line_start} -> {line_end} ({booking_days} días)")
                                
                                # Procesar reserva para nueva reserva
                                self._process_new_reservation(reservations, line, booking, line_start, line_end, booking_id)
                                
                                # Avanzar current_date para la siguiente línea (día siguiente al checkout exclusivo)
                                current_date = line_end
            
            return reservations
            
        except Exception as e:
            _logger.error("Error al obtener reservas: %s", str(e))
            return []
    
    def _process_room_change_reservation(self, reservations, line, booking, line_start, line_end, booking_id):
        """Procesar reserva de cambio de habitación con lógica específica"""
        try:
            # Obtener precio y moneda
            total_amount = booking.get('total_amount', 0.0)
            currency_symbol = ''
            if booking.get('currency_id') and isinstance(booking['currency_id'], (list, tuple)) and len(booking['currency_id']) > 1:
                currency_symbol = booking['currency_id'][1]
            elif booking.get('currency_id') and isinstance(booking['currency_id'], (list, tuple)) and len(booking['currency_id']) > 0:
                try:
                    currency = request.env['res.currency'].sudo().browse(booking['currency_id'][0])
                    if currency.exists():
                        currency_symbol = currency.symbol
                except:
                    currency_symbol = '$'
            else:
                currency_symbol = '$'
            
            # Obtener información de horas del booking original para disponibilidad
            booking_check_in = booking.get('check_in')
            booking_check_out = booking.get('check_out')
            
            # Determinar si el check-in o check-out es a medio día
            check_in_hour = None
            check_out_hour = None
            is_half_day_checkin = False
            is_half_day_checkout = False
            
            if booking_check_in:
                try:
                    check_in_dt = fields.Datetime.context_timestamp(request.env.user, booking_check_in) if hasattr(fields.Datetime, 'context_timestamp') else booking_check_in
                    if isinstance(check_in_dt, datetime):
                        check_in_hour = check_in_dt.hour
                        # Considerar medio día si el check-in es después de las 12:00 PM
                        is_half_day_checkin = check_in_hour >= 12
                except:
                    pass
            
            if booking_check_out:
                try:
                    check_out_dt = fields.Datetime.context_timestamp(request.env.user, booking_check_out) if hasattr(fields.Datetime, 'context_timestamp') else booking_check_out
                    if isinstance(check_out_dt, datetime):
                        check_out_hour = check_out_dt.hour
                        # Considerar medio día si el check-out es antes de las 12:00 PM
                        is_half_day_checkout = check_out_hour < 12
                except:
                    pass
            
            # Crear datos de reserva con información de conexión
            reservation_data = {
                'id': line.get('id', 0),
                'booking_id': booking_id or 0,
                'date_start': line_start.isoformat() if hasattr(line_start, 'isoformat') else str(line_start),
                'date_end': line_end.isoformat() if hasattr(line_end, 'isoformat') else str(line_end),
                'state': booking.get('status_bar', ''),
                'customer_name': booking['partner_id'][1] if booking.get('partner_id') and booking['partner_id'] and len(booking['partner_id']) > 1 else 'N/A',
                'room_id': [line['product_tmpl_id'][0], line['product_tmpl_id'][1]] if line.get('product_tmpl_id') and line['product_tmpl_id'] and len(line['product_tmpl_id']) > 1 else [0, ''],
                'total_amount': total_amount,
                'currency_symbol': currency_symbol,
                'discount_reason': line.get('discount_reason', '') or '',
                'is_room_change': True,  # Marcar como cambio de habitación
                # Información de horas para disponibilidad
                'check_in_hour': check_in_hour,
                'check_out_hour': check_out_hour,
                'is_half_day_checkin': is_half_day_checkin,
                'is_half_day_checkout': is_half_day_checkout,
            }
            
            # Agregar información de conexión para líneas de transición
            if booking.get('connected_booking_id'):
                reservation_data['connected_booking_id'] = booking['connected_booking_id'][0] if isinstance(booking['connected_booking_id'], (list, tuple)) else booking['connected_booking_id']
                reservation_data['is_room_change_origin'] = booking.get('is_room_change_origin', False)
                reservation_data['is_room_change_destination'] = booking.get('is_room_change_destination', False)
            
            reservations.append(reservation_data)
        except Exception as e:
            _logger.error("Error procesando reserva de cambio de habitación: %s", str(e))
    
    def _process_new_reservation(self, reservations, line, booking, line_start, line_end, booking_id):
        """Procesar nueva reserva con lógica específica"""
        try:
            # Obtener precio y moneda
            total_amount = booking.get('total_amount', 0.0)
            currency_symbol = ''
            if booking.get('currency_id') and isinstance(booking['currency_id'], (list, tuple)) and len(booking['currency_id']) > 1:
                currency_symbol = booking['currency_id'][1]
            elif booking.get('currency_id') and isinstance(booking['currency_id'], (list, tuple)) and len(booking['currency_id']) > 0:
                try:
                    currency = request.env['res.currency'].sudo().browse(booking['currency_id'][0])
                    if currency.exists():
                        currency_symbol = currency.symbol
                except:
                    currency_symbol = '$'
            else:
                currency_symbol = '$'
            
            # Obtener información de horas del booking original para disponibilidad
            booking_check_in = booking.get('check_in')
            booking_check_out = booking.get('check_out')
            
            # Determinar si el check-in o check-out es a medio día
            check_in_hour = None
            check_out_hour = None
            is_half_day_checkin = False
            is_half_day_checkout = False
            
            if booking_check_in:
                try:
                    check_in_dt = fields.Datetime.context_timestamp(request.env.user, booking_check_in) if hasattr(fields.Datetime, 'context_timestamp') else booking_check_in
                    if isinstance(check_in_dt, datetime):
                        check_in_hour = check_in_dt.hour
                        # Considerar medio día si el check-in es después de las 12:00 PM
                        is_half_day_checkin = check_in_hour >= 12
                except:
                    pass
            
            if booking_check_out:
                try:
                    check_out_dt = fields.Datetime.context_timestamp(request.env.user, booking_check_out) if hasattr(fields.Datetime, 'context_timestamp') else booking_check_out
                    if isinstance(check_out_dt, datetime):
                        check_out_hour = check_out_dt.hour
                        # Considerar medio día si el check-out es antes de las 12:00 PM
                        is_half_day_checkout = check_out_hour < 12
                except:
                    pass
            
            # Crear datos de reserva con información de conexión
            reservation_data = {
                'id': line.get('id', 0),
                'booking_id': booking_id or 0,
                'date_start': line_start.isoformat() if hasattr(line_start, 'isoformat') else str(line_start),
                'date_end': line_end.isoformat() if hasattr(line_end, 'isoformat') else str(line_end),
                'state': booking.get('status_bar', ''),
                'customer_name': booking['partner_id'][1] if booking.get('partner_id') and booking['partner_id'] and len(booking['partner_id']) > 1 else 'N/A',
                'room_id': [line['product_tmpl_id'][0], line['product_tmpl_id'][1]] if line.get('product_tmpl_id') and line['product_tmpl_id'] and len(line['product_tmpl_id']) > 1 else [0, ''],
                'total_amount': total_amount,
                'currency_symbol': currency_symbol,
                'discount_reason': line.get('discount_reason', '') or '',
                'is_new_reservation': True,  # Marcar como nueva reserva
                # Información de horas para disponibilidad
                'check_in_hour': check_in_hour,
                'check_out_hour': check_out_hour,
                'is_half_day_checkin': is_half_day_checkin,
                'is_half_day_checkout': is_half_day_checkout,
            }
            
            # Agregar información de conexión para líneas de transición
            if booking.get('connected_booking_id'):
                reservation_data['connected_booking_id'] = booking['connected_booking_id'][0] if isinstance(booking['connected_booking_id'], (list, tuple)) else booking['connected_booking_id']
                reservation_data['is_room_change_origin'] = booking.get('is_room_change_origin', False)
                reservation_data['is_room_change_destination'] = booking.get('is_room_change_destination', False)
            
            reservations.append(reservation_data)
        except Exception as e:
            _logger.error("Error procesando nueva reserva: %s", str(e))

    def _build_month_info(self, target_date):
        """Construye la información del mes en el formato requerido por el JS."""
        first_day = target_date.replace(day=1)
        # Calcular el último día del mes
        if target_date.month == 12:
            last_day = target_date.replace(year=target_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            last_day = target_date.replace(month=target_date.month + 1, day=1) - timedelta(days=1)
        
        # Generar la lista de días como números
        days = list(range(1, last_day.day + 1))
        
        return {
            'month_name': target_date.strftime('%B %Y').title(),
            'days': days,
            'first_day_str': first_day.isoformat(),
        }

    @http.route('/hotel/get_product_from_template', type='json', auth='user')
    def get_product_from_template(self, template_id, **kwargs):
        """
        Obtiene el product.product.id correspondiente a un product.template.id
        """
        try:
            _logger.info(f"Buscando product.product para template_id: {template_id}")
            
            if not template_id:
                return {
                    'success': False,
                    'error': 'template_id no proporcionado'
                }
            
            # Buscar el product.product correspondiente al template
            product = request.env['product.product'].sudo().search([
                ('product_tmpl_id', '=', int(template_id))
            ], limit=1)
            
            if product:
                _logger.info(f"Producto encontrado: {product.name} (ID: {product.id})")
                return {
                    'success': True,
                    'product_id': product.id,
                    'product_name': product.name
                }
            else:
                _logger.warning(f"No se encontró product.product para template_id: {template_id}")
                return {
                    'success': False,
                    'error': f'No se encontró producto para el template ID: {template_id}'
                }
                
        except Exception as e:
            _logger.error(f"Error obteniendo product_id para template_id {template_id}: {str(e)}")
            return {
                'success': False,
                'error': f'Error interno: {str(e)}'
            }