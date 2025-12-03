# -*- coding: utf-8 -*-
import json
import logging
from functools import wraps
from odoo import http
from odoo.http import request, Response
from odoo.tools import json_default
from odoo.exceptions import AccessError, ValidationError, UserError
from .api_auth import validate_api_key

_logger = logging.getLogger(__name__)


def handle_exceptions(func):
    """Decorador para manejo centralizado de excepciones."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except AccessError as e:
            _logger.warning(f"Error de acceso en {func.__name__}: {str(e)}")
            return self._error_response(
                'No tiene permisos para acceder a esta información',
                status=403
            )
        except ValidationError as e:
            _logger.error(f"Error de validación en {func.__name__}: {str(e)}")
            return self._error_response(
                f'Error de validación: {str(e)}',
                status=400
            )
        except Exception as e:
            _logger.exception(f"Error inesperado en {func.__name__}: {str(e)}")
            return self._error_response(
                'Error interno del servidor',
                status=500
            )
    return wrapper


class HotelStatesAPIController(http.Controller):
    """
    API REST para gestión de estados del sistema hotelero en Odoo 17.
    
    Proporciona endpoints para consultar estados y transiciones de:
    - hotel.booking: Estados de reservas
    - hotel.housekeeping: Estados de mantenimiento
    
    Módulos relacionados:
    - hotel_management_system (Hotel/)
    - hotel_management_system_extension (ConsultingERP/)
    """

    # Definición centralizada de estados de booking
    BOOKING_STATES = [
        {
            'code': 'initial',
            'name': 'Borrador',
            'name_en': 'Draft',
            'description': 'Reserva en estado inicial, pendiente de confirmación',
            'color': 'secondary',
            'hex_color': '#6c757d',
            'icon': 'fa-file-text-o',
            'is_terminal': False,
            'requires_room': False,
            'requires_payment': False,
            'next_states': ['confirmed', 'cancelled'],
            'order': 1
        },
        {
            'code': 'confirmed',
            'name': 'Confirmada',
            'name_en': 'Confirmed',
            'description': 'Reserva confirmada por el cliente, en espera de check-in',
            'color': 'info',
            'hex_color': '#17a2b8',
            'icon': 'fa-check-circle',
            'is_terminal': False,
            'requires_room': False,
            'requires_payment': True,
            'next_states': ['checkin', 'cancelled', 'no_show'],
            'order': 2
        },
        {
            'code': 'checkin',
            'name': 'Check-in Realizado',
            'name_en': 'Checked In',
            'description': 'Huésped registrado y ocupando la habitación',
            'color': 'success',
            'hex_color': '#28a745',
            'icon': 'fa-sign-in',
            'is_terminal': False,
            'requires_room': True,
            'requires_payment': True,
            'next_states': ['checkout', 'cancelled'],
            'order': 3
        },
        {
            'code': 'checkout',
            'name': 'Check-out Realizado',
            'name_en': 'Checked Out',
            'description': 'Huésped ha finalizado su estancia',
            'color': 'primary',
            'hex_color': '#007bff',
            'icon': 'fa-sign-out',
            'is_terminal': False,
            'requires_room': True,
            'requires_payment': True,
            'next_states': ['cleaning_needed'],
            'order': 4
        },
        {
            'code': 'cleaning_needed',
            'name': 'Limpieza Necesaria',
            'name_en': 'Cleaning Needed',
            'description': 'Habitación requiere limpieza y preparación',
            'color': 'warning',
            'hex_color': '#ffc107',
            'icon': 'fa-broom',
            'is_terminal': False,
            'requires_room': True,
            'requires_payment': False,
            'next_states': ['room_ready'],
            'order': 5
        },
        {
            'code': 'room_ready',
            'name': 'Habitación Lista',
            'name_en': 'Room Ready',
            'description': 'Habitación limpia y lista para nuevo huésped',
            'color': 'success',
            'hex_color': '#28a745',
            'icon': 'fa-thumbs-up',
            'is_terminal': False,
            'requires_room': True,
            'requires_payment': False,
            'next_states': ['confirmed'],
            'order': 6
        },
        {
            'code': 'cancelled',
            'name': 'Cancelada',
            'name_en': 'Cancelled',
            'description': 'Reserva cancelada por el cliente o el sistema',
            'color': 'danger',
            'hex_color': '#dc3545',
            'icon': 'fa-times-circle',
            'is_terminal': True,
            'requires_room': False,
            'requires_payment': False,
            'next_states': ['initial'],
            'can_reactivate': True,
            'order': 7
        },
        {
            'code': 'no_show',
            'name': 'No Se Presentó',
            'name_en': 'No Show',
            'description': 'Cliente no se presentó en la fecha programada',
            'color': 'danger',
            'hex_color': '#dc3545',
            'icon': 'fa-user-times',
            'is_terminal': True,
            'requires_room': False,
            'requires_payment': False,
            'next_states': ['initial'],
            'can_reactivate': True,
            'order': 8
        }
    ]

    # Definición centralizada de estados de housekeeping
    HOUSEKEEPING_STATES = [
        {
            'code': 'draft',
            'name': 'Borrador',
            'name_en': 'Draft',
            'description': 'Tarea de mantenimiento programada, pendiente de inicio',
            'color': 'secondary',
            'hex_color': '#6c757d',
            'icon': 'fa-clock-o',
            'is_terminal': False,
            'next_states': ['in_progress'],
            'order': 1
        },
        {
            'code': 'in_progress',
            'name': 'En Progreso',
            'name_en': 'In Progress',
            'description': 'Mantenimiento o limpieza en curso',
            'color': 'warning',
            'hex_color': '#ffc107',
            'icon': 'fa-spinner',
            'is_terminal': False,
            'next_states': ['completed', 'draft'],
            'order': 2
        },
        {
            'code': 'completed',
            'name': 'Completado',
            'name_en': 'Completed',
            'description': 'Mantenimiento finalizado, habitación verificada',
            'color': 'success',
            'hex_color': '#28a745',
            'icon': 'fa-check-square',
            'is_terminal': True,
            'next_states': [],
            'order': 3
        }
    ]

    def _prepare_response(self, data, status=200):
        """
        Prepara respuesta HTTP JSON.
        
        Args:
            data (dict): Datos a serializar
            status (int): Código HTTP
            
        Returns:
            Response: Respuesta HTTP configurada
        """
        return Response(
            json.dumps(data, default=json_default, ensure_ascii=False),
            status=status,
            content_type='application/json; charset=utf-8',
        )

    def _success_response(self, data, message=None, **kwargs):
        """Respuesta exitosa estandarizada."""
        response_data = {
            'success': True,
            'data': data,
            'timestamp': json_default(request.env.cr.now())
        }
        if message:
            response_data['message'] = message
        response_data.update(kwargs)
        return self._prepare_response(response_data)

    def _error_response(self, error, status=400, code=None):
        """Respuesta de error estandarizada."""
        return self._prepare_response({
            'success': False,
            'error': error,
            'code': code or f'ERROR_{status}',
            'timestamp': json_default(request.env.cr.now())
        }, status=status)

    def _get_state_transitions_graph(self, state_type='booking'):
        """
        Genera un grafo de transiciones de estados.
        
        Args:
            state_type (str): Tipo de estado ('booking' o 'housekeeping')
            
        Returns:
            dict: Grafo de transiciones
        """
        states = self.BOOKING_STATES if state_type == 'booking' else self.HOUSEKEEPING_STATES
        
        graph = {}
        for state in states:
            graph[state['code']] = {
                'name': state['name'],
                'can_transition_to': state.get('next_states', []),
                'is_terminal': state.get('is_terminal', False)
            }
        
        return graph

    @http.route('/api/v1/hotel/states/booking', auth='public', type='http', 
                methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_booking_states(self, **params):
        """
        Obtiene todos los estados disponibles para reservas (hotel.booking).
        
        Query Parameters:
            - include_transitions: Incluir grafo de transiciones (true/false)
            - lang: Idioma para nombres (es/en, default: es)
            
        Returns:
            JSON con lista completa de estados de booking
        """
        include_transitions = params.get('include_transitions', 'false').lower() == 'true'
        lang = params.get('lang', 'es').lower()
        
        # Preparar estados según idioma
        states = []
        for state in self.BOOKING_STATES:
            state_data = state.copy()
            if lang == 'en':
                state_data['name'] = state_data.get('name_en', state_data['name'])
            states.append(state_data)
        
        response_data = {
            'states': states,
            'count': len(states),
            'metadata': {
                'total_states': len(states),
                'terminal_states': len([s for s in states if s.get('is_terminal')]),
                'active_states': len([s for s in states if not s.get('is_terminal')])
            }
        }
        
        # Incluir grafo de transiciones si se solicita
        if include_transitions:
            response_data['transitions'] = self._get_state_transitions_graph('booking')
        
        _logger.info("API: Estados de booking recuperados exitosamente")
        
        return self._success_response(response_data)

    @http.route('/api/v1/hotel/states/booking/<string:state_code>', auth='public', 
                type='http', methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_booking_state_detail(self, state_code, **params):
        """
        Obtiene detalle de un estado específico de booking.
        
        Args:
            state_code (str): Código del estado
            
        Query Parameters:
            - lang: Idioma (es/en, default: es)
            
        Returns:
            JSON con información detallada del estado
        """
        lang = params.get('lang', 'es').lower()
        
        # Buscar el estado
        state = next((s for s in self.BOOKING_STATES if s['code'] == state_code), None)
        
        if not state:
            _logger.info(f"Estado de booking '{state_code}' no encontrado")
            return self._error_response(
                f"Estado con código '{state_code}' no encontrado",
                status=404,
                code='STATE_NOT_FOUND'
            )
        
        state_data = state.copy()
        if lang == 'en':
            state_data['name'] = state_data.get('name_en', state_data['name'])
        
        # Agregar información de estados relacionados
        next_states_detail = [
            {
                'code': next_code,
                'name': next(
                    (s['name'] if lang == 'es' else s.get('name_en', s['name'])
                     for s in self.BOOKING_STATES if s['code'] == next_code),
                    next_code
                )
            }
            for next_code in state_data.get('next_states', [])
        ]
        
        state_data['next_states_detail'] = next_states_detail
        
        _logger.info(f"API: Estado de booking '{state_code}' recuperado exitosamente")
        
        return self._success_response(state_data)

    @http.route('/api/v1/hotel/states/housekeeping', auth='public', type='http', 
                methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_housekeeping_states(self, **params):
        """
        Obtiene todos los estados disponibles para mantenimiento (hotel.housekeeping).
        
        Query Parameters:
            - include_transitions: Incluir grafo de transiciones (true/false)
            - lang: Idioma para nombres (es/en, default: es)
            
        Returns:
            JSON con lista completa de estados de housekeeping
        """
        include_transitions = params.get('include_transitions', 'false').lower() == 'true'
        lang = params.get('lang', 'es').lower()
        
        # Preparar estados según idioma
        states = []
        for state in self.HOUSEKEEPING_STATES:
            state_data = state.copy()
            if lang == 'en':
                state_data['name'] = state_data.get('name_en', state_data['name'])
            states.append(state_data)
        
        response_data = {
            'states': states,
            'count': len(states),
            'metadata': {
                'total_states': len(states),
                'terminal_states': len([s for s in states if s.get('is_terminal')]),
                'active_states': len([s for s in states if not s.get('is_terminal')])
            }
        }
        
        # Incluir grafo de transiciones si se solicita
        if include_transitions:
            response_data['transitions'] = self._get_state_transitions_graph('housekeeping')
        
        _logger.info("API: Estados de housekeeping recuperados exitosamente")
        
        return self._success_response(response_data)

    @http.route('/api/v1/hotel/states/housekeeping/<string:state_code>', auth='public', 
                type='http', methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_housekeeping_state_detail(self, state_code, **params):
        """
        Obtiene detalle de un estado específico de housekeeping.
        
        Args:
            state_code (str): Código del estado
            
        Query Parameters:
            - lang: Idioma (es/en, default: es)
            
        Returns:
            JSON con información detallada del estado
        """
        lang = params.get('lang', 'es').lower()
        
        # Buscar el estado
        state = next((s for s in self.HOUSEKEEPING_STATES if s['code'] == state_code), None)
        
        if not state:
            _logger.info(f"Estado de housekeeping '{state_code}' no encontrado")
            return self._error_response(
                f"Estado con código '{state_code}' no encontrado",
                status=404,
                code='STATE_NOT_FOUND'
            )
        
        state_data = state.copy()
        if lang == 'en':
            state_data['name'] = state_data.get('name_en', state_data['name'])
        
        # Agregar información de estados relacionados
        next_states_detail = [
            {
                'code': next_code,
                'name': next(
                    (s['name'] if lang == 'es' else s.get('name_en', s['name'])
                     for s in self.HOUSEKEEPING_STATES if s['code'] == next_code),
                    next_code
                )
            }
            for next_code in state_data.get('next_states', [])
        ]
        
        state_data['next_states_detail'] = next_states_detail
        
        _logger.info(f"API: Estado de housekeeping '{state_code}' recuperado exitosamente")
        
        return self._success_response(state_data)

    @http.route('/api/v1/hotel/states', auth='public', type='http', 
                methods=['GET'], csrf=False)
    @handle_exceptions
    def get_all_states(self, **params):
        """
        Obtiene todos los estados del sistema hotelero organizados por tipo.
        
        Query Parameters:
            - include_transitions: Incluir grafos de transiciones (true/false)
            - lang: Idioma (es/en, default: es)
            - format: Formato de respuesta (grouped/flat, default: grouped)
            
        Returns:
            JSON con todos los estados organizados por categoría
        """
        include_transitions = params.get('include_transitions', 'false').lower() == 'true'
        lang = params.get('lang', 'es').lower()
        response_format = params.get('format', 'grouped').lower()
        
        # Preparar estados según idioma
        booking_states = []
        for state in self.BOOKING_STATES:
            state_data = state.copy()
            if lang == 'en':
                state_data['name'] = state_data.get('name_en', state_data['name'])
            booking_states.append(state_data)
        
        housekeeping_states = []
        for state in self.HOUSEKEEPING_STATES:
            state_data = state.copy()
            if lang == 'en':
                state_data['name'] = state_data.get('name_en', state_data['name'])
            housekeeping_states.append(state_data)
        
        # Formato agrupado (default)
        if response_format == 'grouped':
            response_data = {
                'booking': {
                    'states': booking_states,
                    'count': len(booking_states),
                    'type': 'hotel.booking',
                    'description': 'Estados de reservas de habitaciones'
                },
                'housekeeping': {
                    'states': housekeeping_states,
                    'count': len(housekeeping_states),
                    'type': 'hotel.housekeeping',
                    'description': 'Estados de mantenimiento y limpieza'
                },
                'summary': {
                    'total_booking_states': len(booking_states),
                    'total_housekeeping_states': len(housekeeping_states),
                    'total_states': len(booking_states) + len(housekeeping_states),
                    'total_terminal_states': (
                        len([s for s in booking_states if s.get('is_terminal')]) +
                        len([s for s in housekeeping_states if s.get('is_terminal')])
                    )
                }
            }
            
            # Incluir transiciones si se solicita
            if include_transitions:
                response_data['transitions'] = {
                    'booking': self._get_state_transitions_graph('booking'),
                    'housekeeping': self._get_state_transitions_graph('housekeeping')
                }
        
        # Formato plano
        else:
            all_states = []
            for state in booking_states:
                state['type'] = 'booking'
                all_states.append(state)
            for state in housekeeping_states:
                state['type'] = 'housekeeping'
                all_states.append(state)
            
            response_data = {
                'states': all_states,
                'total_count': len(all_states)
            }
        
        _logger.info("API: Todos los estados recuperados exitosamente")
        
        return self._success_response(response_data)

    @http.route('/api/v1/hotel/states/validate-transition', auth='public', 
                type='http', methods=['GET'], csrf=False)
    @handle_exceptions
    def validate_state_transition(self, **params):
        """
        Valida si una transición de estado es válida.
        
        Query Parameters:
            - type: Tipo de estado (booking/housekeeping)
            - from_state: Estado origen
            - to_state: Estado destino
            
        Returns:
            JSON indicando si la transición es válida
        """
        state_type = params.get('type', '').lower()
        from_state = params.get('from_state', '').lower()
        to_state = params.get('to_state', '').lower()
        
        # Validar parámetros requeridos
        if not all([state_type, from_state, to_state]):
            return self._error_response(
                'Parámetros requeridos: type, from_state, to_state',
                status=400
            )
        
        if state_type not in ['booking', 'housekeeping']:
            return self._error_response(
                'Tipo de estado inválido. Use: booking o housekeeping',
                status=400
            )
        
        # Obtener estados según tipo
        states = self.BOOKING_STATES if state_type == 'booking' else self.HOUSEKEEPING_STATES
        
        # Buscar estado origen
        origin_state = next((s for s in states if s['code'] == from_state), None)
        
        if not origin_state:
            return self._error_response(
                f"Estado origen '{from_state}' no encontrado",
                status=404
            )
        
        # Validar transición
        valid_transitions = origin_state.get('next_states', [])
        is_valid = to_state in valid_transitions
        
        response_data = {
            'is_valid': is_valid,
            'from_state': {
                'code': from_state,
                'name': origin_state['name']
            },
            'to_state': to_state,
            'valid_transitions': [
                {
                    'code': code,
                    'name': next((s['name'] for s in states if s['code'] == code), code)
                }
                for code in valid_transitions
            ]
        }
        
        if not is_valid:
            response_data['message'] = (
                f"La transición de '{from_state}' a '{to_state}' no es válida"
            )
        
        _logger.info(
            f"API: Validación de transición {from_state} -> {to_state}: {is_valid}"
        )
        
        return self._success_response(response_data)