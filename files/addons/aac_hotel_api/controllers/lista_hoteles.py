import json
import logging
from odoo import http
from odoo.http import request, Response
from odoo.tools import json_default
from odoo.exceptions import AccessError, ValidationError
from .api_auth import validate_api_key

_logger = logging.getLogger(__name__)


class ListaHotelesController(http.Controller):
    """
    Controller para gestionar endpoints de API relacionados con hoteles y habitaciones.
    
    Este controlador está diseñado para trabajar con los módulos:
    - hotel_management_system (Hotel/)
    - hotel_management_system_extension (ConsultingERP/)
    
    Modelos utilizados:
    - hotel.hotels: Modelo principal de hoteles
    - product.template: Modelo de habitaciones (con is_room_type=True)
    """

    def _prepare_response(self, data, status=200):
        """
        Prepara una respuesta HTTP JSON estandarizada.
        
        Args:
            data (dict): Datos a serializar en JSON
            status (int): Código de estado HTTP
            
        Returns:
            Response: Objeto de respuesta HTTP
        """
        return Response(
            json.dumps(data, default=json_default),
            status=status,
            content_type='application/json',
        )

    @http.route('/api/hotel/hoteles', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_hoteles(self, **kw):
        """
        Obtiene la lista de todos los hoteles registrados en el sistema.
        
        Returns:
            Response: JSON con la lista de hoteles o mensaje de error
        """
        try:
            hoteles = request.env['hotel.hotels'].search_read(
                [], 
                ['name', 'partner_id', 'address', 'tagline', 'image', 
                 'banner', 'policies', 'hotel_type_id', 'company_id', 'description', 'is_published']
            )
            
            _logger.info("Consulta exitosa: %d hoteles recuperados", len(hoteles))
            
            return self._prepare_response({
                'success': True,
                'count': len(hoteles),
                'data': hoteles
            })
            
        except AccessError as e:
            _logger.warning("Error de acceso en get_hoteles: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para acceder a esta información'
            }, status=403)
            
        except ValidationError as e:
            _logger.error("Error de validación en get_hoteles: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error de validación en los datos'
            }, status=400)
            
        except Exception as e:
            _logger.exception("Error inesperado en get_hoteles: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/hoteles/<int:hotel_id>', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_hotel_by_id(self, hotel_id, **kw):
        """
        Obtiene un hotel específico por su ID con información completa.
        
        Args:
            hotel_id (int): ID del hotel a consultar
        
        Returns:
            Response: JSON con los datos del hotel o mensaje de error
        """
        try:
            # Validar que el ID sea válido
            if not hotel_id or hotel_id <= 0:
                return self._prepare_response({
                    'success': False,
                    'error': 'ID de hotel inválido'
                }, status=400)
            
            # Buscar el hotel con información completa
            hotel = request.env['hotel.hotels'].search_read(
                [('id', '=', hotel_id), ('active', '=', True)], 
                ['name', 'partner_id', 'address', 'tagline', 'image', 
                 'banner', 'policies', 'hotel_type_id', 'company_id', 'description', 
                 'is_published', 'currency_id', 'default_timezone', 'price_list_id'],
                limit=1
            )
            
            if not hotel:
                _logger.info("Hotel con ID %d no encontrado", hotel_id)
                return self._prepare_response({
                    'success': False,
                    'error': f'Hotel con ID {hotel_id} no encontrado o inactivo'
                }, status=404)
            
            # Obtener información adicional del hotel
            hotel_data = hotel[0]
            
            # Obtener información del partner asociado
            if hotel_data.get('partner_id'):
                partner = request.env['res.partner'].browse(hotel_data['partner_id'][0])
                hotel_data['partner_info'] = {
                    'name': partner.name,
                    'email': partner.email,
                    'phone': partner.phone,
                    'mobile': partner.mobile,
                    'website': partner.website,
                    'street': partner.street,
                    'city': partner.city,
                    'state_id': partner.state_id.name if partner.state_id else None,
                    'country_id': partner.country_id.name if partner.country_id else None,
                    'zip': partner.zip
                }
            
            # Obtener información del tipo de hotel
            if hotel_data.get('hotel_type_id'):
                hotel_type = request.env['hotel.type'].browse(hotel_data['hotel_type_id'][0])
                hotel_data['hotel_type_name'] = hotel_type.hotel_type
            
            # Contar habitaciones asociadas
            room_count = request.env['product.template'].search_count([
                ('is_room_type', '=', True), 
                ('hotel_id', '=', hotel_id),
                ('active', '=', True)
            ])
            hotel_data['room_count'] = room_count
            
            _logger.info("Hotel con ID %d recuperado exitosamente", hotel_id)
            
            return self._prepare_response({
                'success': True,
                'data': hotel_data
            })
            
        except AccessError as e:
            _logger.warning("Error de acceso en get_hotel_by_id: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para acceder a esta información'
            }, status=403)
            
        except ValidationError as e:
            _logger.error("Error de validación en get_hotel_by_id: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error de validación en los datos'
            }, status=400)
            
        except Exception as e:
            _logger.exception("Error inesperado en get_hotel_by_id: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/hoteles/search', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def search_hoteles(self, **kw):
        """
        Busca hoteles con filtros opcionales.
        
        Parámetros de búsqueda:
        - name: Nombre del hotel (búsqueda parcial)
        - city: Ciudad del hotel
        - hotel_type_id: ID del tipo de hotel
        - is_published: Solo hoteles userados (true/false)
        - limit: Límite de resultados (default: 50)
        - offset: Desplazamiento para paginación (default: 0)
        
        Returns:
            Response: JSON con la lista de hoteles filtrados
        """
        try:
            # Obtener parámetros de búsqueda
            name = kw.get('name', '').strip()
            city = kw.get('city', '').strip()
            hotel_type_id = kw.get('hotel_type_id')
            is_published = kw.get('is_published')
            limit = int(kw.get('limit', 50))
            offset = int(kw.get('offset', 0))
            
            # Construir dominio de búsqueda
            domain = [('active', '=', True)]
            
            if name:
                domain.append(('name', 'ilike', name))
            
            if city:
                domain.append(('partner_id.city', 'ilike', city))
            
            if hotel_type_id:
                try:
                    domain.append(('hotel_type_id', '=', int(hotel_type_id)))
                except ValueError:
                    return self._prepare_response({
                        'success': False,
                        'error': 'ID de tipo de hotel inválido'
                    }, status=400)
            
            if is_published is not None:
                domain.append(('is_published', '=', is_published.lower() == 'true'))
            
            # Buscar hoteles
            hoteles = request.env['hotel.hotels'].search_read(
                domain,
                ['name', 'partner_id', 'address', 'tagline', 'image', 
                 'banner', 'policies', 'hotel_type_id', 'company_id', 'description', 
                 'is_published', 'currency_id'],
                limit=limit,
                offset=offset,
                order='name'
            )
            
            # Contar total de resultados
            total_count = request.env['hotel.hotels'].search_count(domain)
            
            _logger.info("Búsqueda de hoteles: %d resultados encontrados", len(hoteles))
            
            return self._prepare_response({
                'success': True,
                'count': len(hoteles),
                'total_count': total_count,
                'offset': offset,
                'limit': limit,
                'data': hoteles
            })
            
        except AccessError as e:
            _logger.warning("Error de acceso en search_hoteles: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para acceder a esta información'
            }, status=403)
            
        except Exception as e:
            _logger.exception("Error inesperado en search_hoteles: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/debug/data', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def debug_data(self, **kw):
        """
        Endpoint de diagnóstico para verificar qué datos están disponibles en el sistema.
        
        Returns:
            Response: JSON con información de debug sobre hoteles y habitaciones
        """
        try:
            # Contar hoteles
            total_hoteles = request.env['hotel.hotels'].search_count([])
            hoteles_activos = request.env['hotel.hotels'].search_count([('active', '=', True)])
            
            # Contar productos/habitaciones
            total_productos = request.env['product.template'].search_count([])
            habitaciones = request.env['product.template'].search_count([('is_room_type', '=', True)])
            habitaciones_activas = request.env['product.template'].search_count([
                ('is_room_type', '=', True), ('active', '=', True)
            ])
            
            # Obtener algunos ejemplos
            hoteles_ejemplo = request.env['hotel.hotels'].search_read(
                [('active', '=', True)], 
                ['id', 'name', 'is_published'], 
                limit=5
            )
            
            habitaciones_ejemplo = request.env['product.template'].search_read(
                [('is_room_type', '=', True), ('active', '=', True)], 
                ['id', 'name', 'hotel_id', 'list_price'], 
                limit=5
            )
            
            return self._prepare_response({
                'success': True,
                'debug_info': {
                    'hoteles': {
                        'total': total_hoteles,
                        'activos': hoteles_activos,
                        'ejemplos': hoteles_ejemplo
                    },
                    'habitaciones': {
                        'total_productos': total_productos,
                        'habitaciones_total': habitaciones,
                        'habitaciones_activas': habitaciones_activas,
                        'ejemplos': habitaciones_ejemplo
                    }
                }
            })
            
        except Exception as e:
            _logger.exception("Error en debug_data: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/hoteles/<int:hotel_id>/cuartos', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_cuartos_by_hotel(self, hotel_id, **kw):
        """
        Obtiene todas las habitaciones asociadas a un hotel específico.
        
        Args:
            hotel_id (int): ID del hotel
        
        Returns:
            Response: JSON con la lista de habitaciones del hotel o mensaje de error
        """
        try:
            # Verificar que el hotel existe
            hotel = request.env['hotel.hotels'].search([('id', '=', hotel_id)], limit=1)
            
            if not hotel:
                _logger.info("Hotel con ID %d no encontrado", hotel_id)
                return self._prepare_response({
                    'success': False,
                    'error': f'Hotel con ID {hotel_id} no encontrado'
                }, status=404)
            
            # Buscar habitaciones asociadas al hotel
            cuartos = request.env['product.template'].search_read(
                [('is_room_type', '=', True), ('hotel_id', '=', hotel_id)],
                ['name', 'list_price', 'max_adult', 'max_child', 'max_infants', 'base_occupancy', 'hotel_id', 'service_ids', 'facility_ids']
            )
            
            _logger.info("Consulta exitosa: %d habitaciones recuperadas para hotel %d", len(cuartos), hotel_id)
            
            return self._prepare_response({
                'success': True,
                'hotel_id': hotel_id,
                'hotel_name': hotel.name,
                'count': len(cuartos),
                'data': cuartos
            })
            
        except AccessError as e:
            _logger.warning("Error de acceso en get_cuartos_by_hotel: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para acceder a esta información'
            }, status=403)
            
        except ValidationError as e:
            _logger.error("Error de validación en get_cuartos_by_hotel: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error de validación en los datos'
            }, status=400)
            
        except Exception as e:
            _logger.exception("Error inesperado en get_cuartos_by_hotel: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/cuartos', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_cuartos(self, **kw):
        """
        Obtiene la lista de todas las habitaciones (productos marcados como room_type).
        
        Returns:
            Response: JSON con la lista de habitaciones o mensaje de error
        """
        try:
            # Consultamos las habitaciones (productos con is_room_type = True)
            cuartos = request.env['product.template'].search_read(
                [('is_room_type', '=', True)],
                ['name', 'id', 'max_adult', 'max_child', 'max_infants', 'base_occupancy', 'service_ids', 'facility_ids']
            )
            
            _logger.info("Consulta exitosa: %d habitaciones recuperadas", len(cuartos))
            
            return self._prepare_response({
                'success': True,
                'count': len(cuartos),
                'data': cuartos
            })
            
        except AccessError as e:
            _logger.warning("Error de acceso en get_cuartos: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para acceder a esta información'
            }, status=403)
            
        except ValidationError as e:
            _logger.error("Error de validación en get_cuartos: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error de validación en los datos'
            }, status=400)
            
        except Exception as e:
            _logger.exception("Error inesperado en get_cuartos: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)

    @http.route('/api/hotel/cuartos/<int:cuarto_id>', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    def get_cuarto_by_id(self, cuarto_id, **kw):
        """
        Obtiene una habitación específica por su ID.
        
        Args:
            cuarto_id (int): ID de la habitación a consultar
        
        Returns:
            Response: JSON con los datos de la habitación o mensaje de error
        """
        try:
            cuarto = request.env['product.template'].search_read(
                [('id', '=', cuarto_id), ('is_room_type', '=', True)],
                ['name', 'id', 'max_adult', 'max_child', 'max_infants', 'base_occupancy', 'service_ids', 'facility_ids'],
                limit=1
            )
            
            if not cuarto:
                # Verificar si el producto existe pero no es habitación
                producto = request.env['product.template'].search([('id', '=', cuarto_id)], limit=1)
                if producto:
                    error_msg = f'Producto con ID {cuarto_id} existe pero no es una habitación (is_room_type=False). Use IDs: 35, 38, 42, 44, 46...'
                else:
                    error_msg = f'Habitación con ID {cuarto_id} no encontrada. Use IDs disponibles: 35, 38, 42, 44, 46...'
                
                _logger.info("Habitación con ID %d no encontrada", cuarto_id)
                return self._prepare_response({
                    'success': False,
                    'error': error_msg
                }, status=404)
            
            _logger.info("Habitación con ID %d recuperada exitosamente", cuarto_id)
            
            return self._prepare_response({
                'success': True,
                'data': cuarto[0]
            })
            
        except AccessError as e:
            _logger.warning("Error de acceso en get_cuarto_by_id: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para acceder a esta información'
            }, status=403)
            
        except ValidationError as e:
            _logger.error("Error de validación en get_cuarto_by_id: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error de validación en los datos'
            }, status=400)
            
        except Exception as e:
            _logger.exception("Error inesperado en get_cuarto_by_id: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': 'Error interno del servidor'
            }, status=500)