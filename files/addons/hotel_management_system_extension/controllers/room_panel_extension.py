import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, date, timezone
from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)

# =============================================================================
# ESTADOS DE RESERVA - IDÉNTICOS A RESERVATION_GANTT
# =============================================================================

# Estados principales (8 estados únicos) - IDÉNTICOS AL RESERVATION_GANTT
ROOM_STATES = {
    'initial': {
        'key': 'initial',
        'label': 'BORRADOR',
        'color': '#A9A9A9',
        'priority': 1,
        'emoji': '⚫'
    },
    'confirmed': {
        'key': 'confirmed',
        'label': 'CONFIRMADA',
        'color': '#00BFA5',
        'priority': 2,
        'emoji': '🟢'
    },
    'checkin': {
        'key': 'checkin',
        'label': 'CHECK-IN',
        'color': '#FF6B35',
        'priority': 3,
        'emoji': '🟠'
    },
    'checkout': {
        'key': 'checkout',
        'label': 'CHECK-OUT',
        'color': '#1A237E',
        'priority': 4,
        'emoji': '🔵'
    },
    'cleaning_needed': {
        'key': 'cleaning_needed',
        'label': 'LIMPIEZA NECESARIA',
        'color': '#FF9800',
        'priority': 5,
        'emoji': '🟡'
    },
    'room_ready': {
        'key': 'room_ready',
        'label': 'HABITACION LISTA',
        'color': '#4CAF50',
        'priority': 6,
        'emoji': '🟢'
    },
    'cancelled': {
        'key': 'cancelled',
        'label': 'CANCELADA',
        'color': '#D32F2F',
        'priority': 7,
        'emoji': '🔴'
    },
    'no_show': {
        'key': 'no_show',
        'label': 'NO SE PRESENTO',
        'color': '#7c5bba',
        'priority': 8,
        'emoji': '🟣'
    }
}

# Mapeo directo de estados de reserva - UNIFICADO CON RESERVATION_GANTT
BOOKING_TO_ROOM_STATE = {
    # Estados principales del Gantt - MAPPING DIRECTO
    'initial': 'initial',           # BORRADOR → BORRADOR
    'confirmed': 'confirmed',       # CONFIRMADA → CONFIRMADA
    'checkin': 'checkin',           # CHECK-IN → CHECK-IN
    'checkout': 'checkout',         # CHECK-OUT → CHECK-OUT
    'cleaning_needed': 'cleaning_needed', # LIMPIEZA NECESARIA → LIMPIEZA NECESARIA
    'room_ready': 'room_ready',     # HABITACION LISTA → HABITACION LISTA
    'cancelled': 'cancelled',       # CANCELADA → CANCELADA
    'no_show': 'no_show',           # NO SE PRESENTO → NO SE PRESENTO
    
    # Estados legacy (compatibilidad) - Mapeados a estados del Gantt
    'draft': 'initial',             # draft → initial (BORRADOR)
    'confirm': 'confirmed',         # confirm → confirmed (CONFIRMADA)
    'allot': 'checkin',             # allot → checkin (CHECK-IN)
    'check_in': 'checkin',          # check_in → checkin (CHECK-IN)
    'checkout_pending': 'checkout', # checkout_pending → checkout (CHECK-OUT)
    'pending': 'confirmed',         # pending → confirmed (CONFIRMADA)
    'room_assigned': 'checkin',     # room_assigned → checkin (CHECK-IN)
    'cancel': 'cancelled',          # cancel → cancelled (CANCELADA)
    'done': 'room_ready'            # done → room_ready (HABITACION LISTA)
}


class RoomPanelControllerExtension(http.Controller):
    
    def _get_or_create_default_partner(self):
        """
        Obtiene o crea un cliente por defecto para reservas rápidas.
        Reutiliza la misma lógica del Gantt para consistencia.
        """
        try:
            # Buscar cliente por defecto existente
            default_partner = request.env['res.partner'].sudo().search([
                ('name', '=', 'Cliente de Paso'),
                ('is_company', '=', False)
            ], limit=1)
            
            if not default_partner:
                # Obtener país de Perú para el cliente por defecto
                country_pe = request.env['res.country'].sudo().search([('code', '=', 'PE')], limit=1)
                
                # Crear cliente por defecto
                default_partner = request.env['res.partner'].sudo().create({
                    'name': 'Cliente de Paso',
                    'is_company': False,
                    'email': 'cliente.paso@hotel.com',
                    'phone': '+51 999 999 999',
                    'street': 'Dirección Temporal',
                    'city': 'Ciudad',
                    'country_id': country_pe.id if country_pe else False,
                })
            
            return default_partner.id
            
        except Exception as e:
            _logger.error("Error creando cliente por defecto: %s", str(e))
            return False
    
    @http.route('/hotel/get_default_partner', type='json', auth='user')
    def get_default_partner(self, **kwargs):
        """
        Endpoint para obtener cliente por defecto.
        Reutiliza la misma lógica del Gantt.
        """
        try:
            default_partner_id = self._get_or_create_default_partner()
            
            return {
                'success': bool(default_partner_id),
                'default_partner_id': default_partner_id if default_partner_id else None,
                'error': None if default_partner_id else 'No se pudo obtener cliente por defecto'
            }
            
        except Exception as e:
            _logger.error("Error en get_default_partner: %s", str(e))
            return {
                'success': False,
                'error': str(e)
            }
    
    @http.route('/hotel/room_panel_data', type='json', auth='user')
    def get_room_panel_data(self, hotel_id: Optional[int] = None, **kwargs) -> Dict[str, Any]:
        """Obtiene los datos del panel de habitaciones"""
        
        # Inicializar con valores por defecto
        rooms = []
        reservations = []
        
        try:
            # Usar transacción explícita para evitar problemas
            with request.env.cr.savepoint():
                rooms = self._get_rooms_data(hotel_id)
                room_ids = [room['id'] for room in rooms] if rooms else []
                
                if room_ids:
                    reservations = self._get_reservations_for_rooms(room_ids)

            return {
                'success': True,
                'rooms': rooms,
                'reservations': reservations,
            }
            
        except Exception as e:
            _logger.error("Error crítico en get_room_panel_data: %s", e, exc_info=True)
            
            # En caso de error, intentar devolver al menos las habitaciones básicas
            try:
                with request.env.cr.savepoint():
                    basic_rooms = self._get_basic_rooms_data(hotel_id)
                    return {
                        'success': True,
                        'rooms': basic_rooms,
                        'reservations': [],
                        'warning': 'Datos limitados debido a error en consulta completa'
                    }
            except Exception:
                return {
                    'success': False, 
                    'error': f'Error al cargar datos del panel: {str(e)}'
                }

    @http.route('/hotel/room_change_info/<int:booking_id>', type='json', auth='user')
    def get_room_change_info(self, booking_id: int, **kwargs) -> Dict[str, Any]:
        """
        Obtiene información de vínculos de cambio de habitación para una reserva específica.
        ADAPTADO: Para manejar los nuevos campos de vínculo logístico.
        """
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            if not booking.exists():
                return {'success': False, 'error': 'Reserva no encontrada'}
            
            # Obtener información de vínculos
            room_change_info = {
                'booking_id': booking_id,
                'split_from_booking_id': booking.split_from_booking_id.id if booking.split_from_booking_id else None,
                'connected_booking_id': booking.connected_booking_id.id if booking.connected_booking_id else None,
                'is_room_change_origin': booking.is_room_change_origin,
                'is_room_change_destination': booking.is_room_change_destination,
                'has_room_change': bool(booking.split_from_booking_id or booking.connected_booking_id)
            }
            
            # Si tiene reserva original, obtener información adicional
            if booking.split_from_booking_id:
                original_booking = booking.split_from_booking_id
                room_change_info['original_booking'] = {
                    'id': original_booking.id,
                    'guest_name': original_booking.partner_id.name if original_booking.partner_id else 'Huésped',
                    'check_in': original_booking.check_in.isoformat() if original_booking.check_in else None,
                    'check_out': original_booking.check_out.isoformat() if original_booking.check_out else None,
                    'status': original_booking.status_bar
                }
            
            # Si tiene reserva conectada, obtener información adicional
            if booking.connected_booking_id:
                connected_booking = booking.connected_booking_id
                room_change_info['connected_booking'] = {
                    'id': connected_booking.id,
                    'guest_name': connected_booking.partner_id.name if connected_booking.partner_id else 'Huésped',
                    'check_in': connected_booking.check_in.isoformat() if connected_booking.check_in else None,
                    'check_out': connected_booking.check_out.isoformat() if connected_booking.check_out else None,
                    'status': connected_booking.status_bar
                }
            
            return {
                'success': True,
                'room_change_info': room_change_info
            }
            
        except Exception as e:
            _logger.error("Error obteniendo información de cambio de habitación: %s", e, exc_info=True)
            return {'success': False, 'error': str(e)}

    @http.route('/hotel/room_panel_filters', type='json', auth='user')
    def get_room_panel_filters(self, **kwargs) -> Dict[str, Any]:
        """Obtiene los datos para los filtros del panel"""
        
        try:    
            # Obtener hoteles activos
            hotels = request.env['hotel.hotels'].search_read(
                [('active', '=', True)], 
                ['id', 'name'], 
                order='name asc'
            )
            
            # Obtener tipos de habitación con categoría
            rooms_with_category = request.env['product.template'].search_read(
                [('is_room_type', '=', True), ('categ_id', '!=', False)],
                ['categ_id']
            )
            
            room_types = []
            if rooms_with_category:
                # Extraer IDs de categorías de forma segura
                category_ids = []
                for rec in rooms_with_category:
                    categ_data = rec.get('categ_id')
                    if categ_data and isinstance(categ_data, (list, tuple)) and len(categ_data) >= 1:
                        category_ids.append(categ_data[0])
                
                # Eliminar duplicados
                category_ids = list(set(category_ids))
                
                if category_ids:
                    room_types = request.env['product.category'].search_read(
                        [('id', 'in', category_ids)], 
                        ['id', 'name'], 
                        order='name asc'
                    )

            # Estados de reserva principales (8 estados únicos) - IDÉNTICOS AL RESERVATION_GANTT
            reservation_states = [
                {'key': 'initial', 'label': 'BORRADOR', 'color': '#A9A9A9', 'priority': 1, 'emoji': '⚫'},
                {'key': 'confirmed', 'label': 'CONFIRMADA', 'color': '#00BFA5', 'priority': 2, 'emoji': '🟢'},
                {'key': 'checkin', 'label': 'CHECK-IN', 'color': '#FF6B35', 'priority': 3, 'emoji': '🟠'},
                {'key': 'checkout', 'label': 'CHECK-OUT', 'color': '#1A237E', 'priority': 4, 'emoji': '🔵'},
                {'key': 'cleaning_needed', 'label': 'LIMPIEZA NECESARIA', 'color': '#FF9800', 'priority': 5, 'emoji': '🟡'},
                {'key': 'room_ready', 'label': 'HABITACION LISTA', 'color': '#4CAF50', 'priority': 6, 'emoji': '🟢'},
                {'key': 'cancelled', 'label': 'CANCELADA', 'color': '#D32F2F', 'priority': 7, 'emoji': '🔴'},
                {'key': 'no_show', 'label': 'NO SE PRESENTO', 'color': '#7c5bba', 'priority': 8, 'emoji': '🟣'},
            ]
            
            return {
                'success': True,
                'hotels': hotels,
                'room_types': room_types,
                'available_states': reservation_states,
            }
            
        except Exception as e:
            _logger.error("Error cargando datos de filtros: %s", e, exc_info=True)
            return {'success': False, 'error': str(e)}

    def _get_rooms_data(self, hotel_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Obtiene los datos de las habitaciones"""
        
        domain = [('is_room_type', '=', True)]
        
        if hotel_id:
            try:
                domain.append(('hotel_id', '=', int(hotel_id)))
            except (ValueError, TypeError):
                _logger.warning("Formato de hotel_id inválido ignorado: %s", hotel_id)

        fields_to_read = [
            'id', 'name', 'default_code', 'list_price', 'hotel_id',
            'categ_id', 'max_adult', 'max_child',
            'product_website_description', 'image_1920',
            'product_tag_ids'
        ]
        
        rooms = request.env['product.template'].search_read(domain, fields_to_read, order='name asc')
        
        # Procesar etiquetas para obtener nombres completos
        self._process_room_tags(rooms)

        # Obtener reservas actuales para determinar estados de habitaciones
        room_states = self._calculate_room_states([room['id'] for room in rooms])

        processed_rooms = []
        for room in rooms:
            processed_room = self._process_single_room(room, room_states)
            processed_rooms.append(processed_room)
            
        return processed_rooms

    def _process_room_tags(self, rooms: List[Dict[str, Any]]) -> None:
        """Procesa las etiquetas de las habitaciones para obtener nombres completos"""
        
        for room in rooms:
            if room.get('product_tag_ids'):
                tag_ids = room['product_tag_ids']
                if isinstance(tag_ids, list) and tag_ids:
                    # Buscar etiquetas por IDs
                    tags = request.env['product.tag'].sudo().browse(tag_ids)
                    # Convertir a formato [id, name]
                    room['product_tag_ids'] = [[tag.id, tag.name] for tag in tags if tag.exists()]
                else:
                    room['product_tag_ids'] = []
            else:
                room['product_tag_ids'] = []

    def _process_single_room(self, room: Dict[str, Any], room_states: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
        """Procesa una habitación individual con sus datos y estado"""
        
        room_id = room['id']
        
        # Calcular capacidad total
        capacity = room.get('max_adult', 0) + room.get('max_child', 0)
        
        # Obtener estado actual e información de reserva
        room_state_info = room_states.get(room_id, {
            'status': 'room_ready',
            'current_reservation': None,
            'next_reservation': None
        })
        
        return {
            'id': room_id,
            'name': room.get('name'),
            'code': room.get('default_code'),
            'list_price': room.get('list_price', 0.0),
            'hotel_id': room.get('hotel_id'),
            'categ_id': room.get('categ_id'),
            'max_adult': room.get('max_adult', 0),
            'max_child': room.get('max_child', 0),
            'capacity': capacity,
            'status': room_state_info['status'],
            'current_reservation': room_state_info['current_reservation'],
            'next_reservation': room_state_info['next_reservation'],
            'features': room.get('product_website_description'),
            'image_1920': room.get('image_1920'),
            'product_tag_ids': room.get('product_tag_ids'),
            'last_updated': fields.Datetime.now().isoformat(),
        }

    def _get_basic_rooms_data(self, hotel_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Método de respaldo para obtener datos básicos de habitaciones sin cálculos complejos.
        """
        try:
            domain = [('is_room_type', '=', True)]
            if hotel_id:
                try:
                    domain.append(('hotel_id', '=', int(hotel_id)))
                except (ValueError, TypeError):
                    _logger.warning("Formato de hotel_id inválido ignorado: %s", hotel_id)

            fields_to_read = [
                'id', 'name', 'default_code', 'list_price', 'hotel_id',
                'categ_id', 'max_adult', 'max_child', 'image_1920'
            ]
            
            rooms = request.env['product.template'].search_read(
                domain, fields_to_read, order='name asc'
            )
            
            basic_rooms = []
            for room in rooms:
                capacity = room.get('max_adult', 0) + room.get('max_child', 0)
                
                basic_rooms.append({
                    'id': room['id'],
                    'name': room.get('name'),
                    'code': room.get('default_code'),
                    'list_price': room.get('list_price', 0.0),
                    'hotel_id': room.get('hotel_id'),
                    'categ_id': room.get('categ_id'),
                    'max_adult': room.get('max_adult', 0),
                    'max_child': room.get('max_child', 0),
                    'capacity': capacity,
                    'status': 'room_ready',  # Estado por defecto (IDÉNTICO AL GANTT)
                    'current_reservation': None,
                    'next_reservation': None,
                    'features': None,
                    'image_1920': room.get('image_1920'),
                    'product_tag_ids': [],
                    'last_updated': fields.Datetime.now().isoformat(),
                })
            
            return basic_rooms
            
        except Exception as e:
            _logger.error("Error en _get_basic_rooms_data: %s", e, exc_info=True)
            return []

    def _calculate_room_states(self, room_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Calcula el estado actual de cada habitación basado en las reservas activas.
        Versión simplificada para evitar errores de transacción.
        """
        room_states = {}
        
        if not room_ids:
            return room_states

        # Inicializar todas las habitaciones como room_ready (IDÉNTICO AL GANTT)
        self._initialize_room_states(room_states, room_ids)

        # PASO 1: Procesar reservas canceladas
        self._process_cancelled_reservations(room_states, room_ids)

        # PASO 2: Procesar todas las reservas activas
        self._process_active_reservations(room_states, room_ids)

        return room_states

    def _initialize_room_states(self, room_states: Dict[int, Dict[str, Any]], room_ids: List[int]) -> None:
        """Inicializa los estados de las habitaciones"""
        for room_id in room_ids:
            room_states[room_id] = {
                'status': 'room_ready',
                'current_reservation': None,
                'next_reservation': None
            }

    def _process_cancelled_reservations(self, room_states: Dict[int, Dict[str, Any]], room_ids: List[int]) -> None:
        """Procesa las reservas canceladas para convertirlas a room_ready"""
        try:
            cancelled_query = """
                SELECT DISTINCT pp.product_tmpl_id as room_id
                FROM hotel_booking_line hbl
                JOIN hotel_booking hb ON hbl.booking_id = hb.id
                JOIN product_product pp ON hbl.product_id = pp.id
                WHERE pp.product_tmpl_id = ANY(%s)
                    AND hb.status_bar = 'cancel'
            """
            
            request.env.cr.execute(cancelled_query, [room_ids])
            cancelled_results = request.env.cr.dictfetchall()
            
            # Forzar todas las habitaciones con reservas canceladas a room_ready
            for cancelled_row in cancelled_results:
                cancelled_room_id = cancelled_row['room_id']
                if cancelled_room_id in room_states:
                    room_states[cancelled_room_id].update({
                        'status': 'room_ready',
                        'current_reservation': None,
                        'next_reservation': None
                    })
                    
        except Exception as e:
            _logger.error("Error procesando reservas canceladas: %s", e)

    def _process_active_reservations(self, room_states: Dict[int, Dict[str, Any]], room_ids: List[int]) -> None:
        """Procesa todas las reservas activas"""
        try:
            # Usar una consulta más simple y directa
            # ADAPTADO: Incluir información de vínculos de cambio de habitación
            all_reservations_query = """
                SELECT DISTINCT 
                    pp.product_tmpl_id as room_id,
                    hb.id as booking_id,
                    hb.check_in,
                    hb.check_out,
                    hb.status_bar,
                    rp.name as guest_name,
                    hbl.product_id as product_product_id,
                    hb.split_from_booking_id,
                    hb.connected_booking_id,
                    hb.is_room_change_origin,
                    hb.is_room_change_destination
                FROM hotel_booking_line hbl
                JOIN hotel_booking hb ON hbl.booking_id = hb.id
                JOIN product_product pp ON hbl.product_id = pp.id
                LEFT JOIN res_partner rp ON hb.partner_id = rp.id
                WHERE pp.product_tmpl_id = ANY(%s)
                    AND hb.status_bar NOT IN ('cancel', 'cancelled')
                ORDER BY pp.product_tmpl_id, hb.check_in
            """
            
            request.env.cr.execute(all_reservations_query, [room_ids])
            all_results = request.env.cr.dictfetchall()
            
            # Procesar cada reserva
            for row in all_results:
                self._process_single_reservation(row, room_states)
                
        except Exception as e:
            _logger.error("Error calculando estados de habitaciones: %s", e, exc_info=True)
            # En caso de error, mantener estados por defecto
            for room_id in room_ids:
                if room_id not in room_states:
                    room_states[room_id] = {
                        'status': 'room_ready',
                        'current_reservation': None,
                        'next_reservation': None
                    }

    def _process_single_reservation(self, row: Dict[str, Any], room_states: Dict[int, Dict[str, Any]]) -> None:
        """Procesa una reserva individual"""
        room_id = row['room_id']
        if room_id not in room_states:
            return
            
        checkin_date = row['check_in']
        checkout_date = row['check_out']
        booking_status = row['status_bar']
        
        # Normalizar fechas
        try:
            checkin_dt, checkout_dt = self._normalize_reservation_dates(checkin_date, checkout_date)
            if not checkin_dt or not checkout_dt:
                return
                
            # Convertir a zona del usuario para mostrar
            local_checkin_dt = fields.Datetime.context_timestamp(request.env.user, checkin_dt)
            local_checkout_dt = fields.Datetime.context_timestamp(request.env.user, checkout_dt)
            local_checkin_str = local_checkin_dt.strftime('%Y-%m-%dT%H:%M:%S')
            local_checkout_str = local_checkout_dt.strftime('%Y-%m-%dT%H:%M:%S')
            
            # ADAPTADO: Crear payload de reserva con información de vínculos
            reservation_payload = {
                'id': row['booking_id'],
                'guest_name': row['guest_name'] or 'Huésped',
                'status': booking_status,
                'checkin_date': local_checkin_str,
                'checkout_date': local_checkout_str,
                # Información de vínculos de cambio de habitación
                'split_from_booking_id': row.get('split_from_booking_id'),
                'connected_booking_id': row.get('connected_booking_id'),
                'is_room_change_origin': row.get('is_room_change_origin', False),
                'is_room_change_destination': row.get('is_room_change_destination', False),
                'is_room_change': bool(row.get('split_from_booking_id') or row.get('connected_booking_id'))
            }
            
            # Procesar según el tipo de estado
            self._update_room_state_by_booking_status(
                room_id, booking_status, checkin_dt, checkout_dt, 
                reservation_payload, room_states
            )
            
        except Exception as e:
            _logger.warning("Error procesando fechas para habitación %s: %s", room_id, e)

    def _normalize_reservation_dates(self, checkin_date, checkout_date):
        """Normaliza las fechas de reserva a datetime UTC"""
        try:
            # Normalizar checkin
            if isinstance(checkin_date, str):
                checkin_dt = datetime.fromisoformat(checkin_date.replace(' ', 'T').replace('Z', '+00:00'))
                if checkin_dt.tzinfo is not None:
                    checkin_dt = checkin_dt.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                checkin_dt = checkin_date

            # Normalizar checkout
            if isinstance(checkout_date, str):
                checkout_dt = datetime.fromisoformat(checkout_date.replace(' ', 'T').replace('Z', '+00:00'))
                if checkout_dt.tzinfo is not None:
                    checkout_dt = checkout_dt.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                checkout_dt = checkout_date

            return checkin_dt, checkout_dt
            
        except Exception:
            return None, None

    def _handle_room_change_reservation(self, room_id: int, booking_status: str,
                                      checkin_dt: datetime, checkout_dt: datetime,
                                      reservation_payload: Dict[str, Any], 
                                      room_states: Dict[int, Dict[str, Any]],
                                      now_date, checkin_date_only, checkout_date_only, mapped_status) -> None:
        """
        Maneja la lógica especial para reservas con cambio de habitación.
        ADAPTADO: Considera el cambio en el cálculo de fechas (original_end_date = change_start)
        """
        try:
            # Para reservas que son origen de cambio (acortadas)
            if reservation_payload.get('is_room_change_origin'):
                # La reserva original se acorta y termina en change_start (no change_start - 1 día)
                # Por lo tanto, si hoy es >= checkin_date y < checkout_date, está activa
                if checkin_date_only <= now_date < checkout_date_only:
                    room_states[room_id]['status'] = mapped_status
                    room_states[room_id]['current_reservation'] = reservation_payload
                    # Agregar indicador de que es reserva acortada
                    reservation_payload['is_shortened_booking'] = True
                return
            
            # Para reservas que son destino de cambio (nuevas)
            if reservation_payload.get('is_room_change_destination'):
                # La nueva reserva comienza en change_start y continúa hasta checkout
                if checkin_date_only <= now_date <= checkout_date_only:
                    room_states[room_id]['status'] = mapped_status
                    room_states[room_id]['current_reservation'] = reservation_payload
                    # Agregar indicador de que es reserva de continuación
                    reservation_payload['is_continuation_booking'] = True
                elif now_date < checkin_date_only and not room_states[room_id]['next_reservation']:
                    room_states[room_id]['next_reservation'] = reservation_payload
                    reservation_payload['is_continuation_booking'] = True
                return
            
            # Para reservas con vínculo pero sin flags específicos (casos edge)
            if reservation_payload.get('split_from_booking_id') or reservation_payload.get('connected_booking_id'):
                # Aplicar lógica estándar pero con indicador de cambio
                reservation_payload['has_room_change_link'] = True
                # Continuar con lógica estándar...
                
        except Exception as e:
            _logger.warning("Error manejando reserva con cambio de habitación: %s", e)
            # En caso de error, aplicar lógica estándar
            pass

    def _update_room_state_by_booking_status(self, room_id: int, booking_status: str, 
                                           checkin_dt: datetime, checkout_dt: datetime,
                                           reservation_payload: Dict[str, Any], 
                                           room_states: Dict[int, Dict[str, Any]]) -> None:
        """Actualiza el estado de la habitación según el estado de la reserva"""
        
        now_date = fields.Date.context_today(request.env.user)
        checkin_date_only = checkin_dt.date()
        checkout_date_only = checkout_dt.date()
        
        # Mapear estado usando BOOKING_TO_ROOM_STATE
        mapped_status = BOOKING_TO_ROOM_STATE.get(booking_status, booking_status)
        
        # ADAPTADO: Lógica especial para reservas con cambio de habitación
        if reservation_payload.get('is_room_change'):
            self._handle_room_change_reservation(
                room_id, booking_status, checkin_dt, checkout_dt, 
                reservation_payload, room_states, now_date, 
                checkin_date_only, checkout_date_only, mapped_status
            )
            return
        
        # LÓGICA ESPECIAL PARA BORRADORES: Procesar sin importar fechas
        if booking_status in ('initial', 'draft'):
            room_states[room_id]['status'] = 'initial'
            room_states[room_id]['current_reservation'] = reservation_payload
            return
        
        # LÓGICA ESPECIAL PARA CONFIRMADAS: comparar por FECHA (no por hora)
        if booking_status in ('confirmed', 'confirm', 'pending'):
            if now_date <= checkout_date_only:
                room_states[room_id]['status'] = 'confirmed'
                if now_date < checkin_date_only and not room_states[room_id]['next_reservation']:
                    room_states[room_id]['next_reservation'] = reservation_payload
                else:
                    room_states[room_id]['current_reservation'] = reservation_payload
                return

        # LÓGICA ESPECIAL PARA CHECK-IN: comparar por FECHA (no por hora)
        if booking_status in ('checkin', 'allot', 'check_in'):
            if checkin_date_only <= now_date <= checkout_date_only:
                room_states[room_id]['status'] = 'checkin'
                room_states[room_id]['current_reservation'] = reservation_payload
                return
            if now_date < checkin_date_only and not room_states[room_id]['next_reservation']:
                room_states[room_id]['status'] = 'checkin'
                room_states[room_id]['next_reservation'] = reservation_payload
                return

        # LÓGICA ESPECIAL PARA CHECK-OUT: comparar por FECHA (no por hora)
        if booking_status in ('checkout', 'check_out'):
            if now_date >= checkout_date_only:
                room_states[room_id]['status'] = 'cleaning_needed'
                room_states[room_id]['current_reservation'] = reservation_payload
                return
            if now_date < checkout_date_only:
                room_states[room_id]['status'] = 'checkout'
                room_states[room_id]['current_reservation'] = reservation_payload
                return

        # LÓGICA ESPECIAL PARA LIMPIEZA NECESARIA: mantener estado
        if booking_status in ('cleaning_needed', 'cleaning'):
            room_states[room_id]['status'] = 'cleaning_needed'
            room_states[room_id]['current_reservation'] = reservation_payload
            return

        # Determinar si es reserva actual o futura (para no-borradores)
        now = fields.Datetime.now()
        
        if checkin_dt <= now <= checkout_dt:
            # Reserva activa
            room_states[room_id]['status'] = mapped_status
            room_states[room_id]['current_reservation'] = reservation_payload
        elif checkin_dt > now and not room_states[room_id]['next_reservation']:
            # Próxima reserva
            room_states[room_id]['status'] = mapped_status
            room_states[room_id]['next_reservation'] = reservation_payload

    def _format_reservation_for_panel(self, booking: Dict[str, Any]) -> Dict[str, Any]:
        """Formatea datos de reserva para el panel."""
        partner_data = booking.get('partner_id')
        partner_name = partner_data[1] if partner_data and len(partner_data) > 1 else 'Huésped'
        
        hotel_data = booking.get('hotel_id')
        hotel_name = hotel_data[1] if hotel_data and len(hotel_data) > 1 else 'Hotel'
        
        checkin = booking.get('check_in')
        checkout = booking.get('check_out')
        
        # Formatear fechas
        checkin_str = self._format_date_for_display(checkin)
        checkout_str = self._format_date_for_display(checkout)

        status_key = booking.get('status_bar', 'unknown')
        status_info = ROOM_STATES.get(status_key, {})

        return {
            'id': booking['id'],
            'guest_name': partner_name,
            'hotel_name': hotel_name,
            'status': status_key,
            'status_label': status_info.get('label', 'Desconocido'),
            'status_color': status_info.get('color', '#6c757d'),
            'status_emoji': status_info.get('emoji', '❓'),
            'checkin_date': checkin_str,
            'checkout_date': checkout_str
        }

    def _format_date_for_display(self, date_value) -> Optional[str]:
        """Formatea una fecha para mostrar"""
        if not date_value:
            return None
            
        try:
            if isinstance(date_value, str):
                date_obj = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
            else:
                date_obj = date_value
                
            return date_obj.strftime('%Y-%m-%d %H:%M')
            
        except Exception:
            return None

    def _get_reservations_for_rooms(self, room_ids: List[int]) -> List[Dict[str, Any]]:
        """
        Obtiene las reservas para las habitaciones especificadas.
        Versión simplificada para evitar errores de transacción.
        """
        if not room_ids:
            return []
        
        try:
            # Usar consulta SQL directa para evitar problemas de ORM
            today_str = fields.Date.today().strftime('%Y-%m-%d')
            
            # ADAPTADO: Incluir información de vínculos de cambio de habitación
            query = """
                SELECT 
                    hb.id as booking_id,
                    hb.status_bar,
                    hb.check_in,
                    hb.check_out,
                    rp.name as guest_name,
                    pt.id as product_id,
                    pt.name as product_name,
                    hb.split_from_booking_id,
                    hb.connected_booking_id,
                    hb.is_room_change_origin,
                    hb.is_room_change_destination
                FROM hotel_booking_line hbl
                JOIN hotel_booking hb ON hbl.booking_id = hb.id
                JOIN product_product pp ON hbl.product_id = pp.id
                JOIN product_template pt ON pp.product_tmpl_id = pt.id
                LEFT JOIN res_partner rp ON hb.partner_id = rp.id
                WHERE pt.id = ANY(%s)
                    AND hb.status_bar NOT IN ('cancelled', 'no_show')
                    AND DATE(hb.check_in) = %s
                ORDER BY hb.check_in
            """
            
            request.env.cr.execute(query, [room_ids, today_str])
            results = request.env.cr.dictfetchall()
            
            reservation_list = []
            for row in results:
                formatted_reservation = self._format_reservation_from_query(row)
                if formatted_reservation:
                    reservation_list.append(formatted_reservation)
                
            return reservation_list
            
        except Exception as e:
            _logger.error("Error obteniendo reservas para habitaciones: %s", e, exc_info=True)
            return []

    def _format_reservation_from_query(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Formatea una reserva desde los resultados de la consulta"""
        try:
            checkin_date = row['check_in']
            checkout_date = row['check_out']
            
            # Formatear fechas
            checkin_str = self._format_date_simple(checkin_date)
            checkout_str = self._format_date_simple(checkout_date)

            # ADAPTADO: Incluir información de vínculos de cambio de habitación
            return {
                'id': row['booking_id'],
                'state': row['status_bar'] or 'unknown',
                'guest_name': row['guest_name'] or 'Huésped',
                'date_start': checkin_str,
                'date_end': checkout_str,
                'room_id': [row['product_id'], row['product_name'] or ''],
                # Información de vínculos de cambio de habitación
                'split_from_booking_id': row.get('split_from_booking_id'),
                'connected_booking_id': row.get('connected_booking_id'),
                'is_room_change_origin': row.get('is_room_change_origin', False),
                'is_room_change_destination': row.get('is_room_change_destination', False),
                'has_room_change': bool(row.get('split_from_booking_id') or row.get('connected_booking_id'))
            }
        except Exception as e:
            _logger.warning("Error formateando reserva: %s", e)
            return None

    def _format_date_simple(self, date_value) -> Optional[str]:
        """Formatea una fecha de forma simple (solo fecha)"""
        if not date_value:
            return None
            
        try:
            if isinstance(date_value, str):
                return date_value[:10]  # Solo la fecha YYYY-MM-DD
            else:
                return date_value.strftime('%Y-%m-%d')
        except Exception:
            return None