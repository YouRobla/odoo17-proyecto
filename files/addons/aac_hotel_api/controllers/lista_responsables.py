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
        except UserError as e:
            _logger.error(f"Error de usuario en {func.__name__}: {str(e)}")
            return self._error_response(str(e), status=400)
        except ValueError as e:
            _logger.error(f"Error de valor en {func.__name__}: {str(e)}")
            return self._error_response(
                'Parámetros inválidos en la solicitud',
                status=400
            )
        except Exception as e:
            _logger.exception(f"Error inesperado en {func.__name__}: {str(e)}")
            return self._error_response(
                'Error interno del servidor',
                status=500
            )
    return wrapper


class ResponsablesAPIController(http.Controller):
    """
    API REST para gestión de responsables (res.users) en Odoo 17.
    
    Proporciona endpoints para consultar y buscar usuarios responsables
    que pueden ser asignados a reservas de hotel.
    """

    # Campos base para listados
    FIELDS_LIST = [
        'id', 'name', 'login', 'email', 'phone', 'mobile',
        'image_128', 'active', 'company_id'
    ]

    # Campos completos para detalle
    FIELDS_DETAIL = FIELDS_LIST + [
        'image_1920', 'groups_id', 'partner_id', 'tz', 'lang',
        'signature', 'function', 'title', 'website', 'street',
        'city', 'state_id', 'country_id', 'zip'
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
        response_data = {'success': True, 'data': data}
        if message:
            response_data['message'] = message
        response_data.update(kwargs)
        return self._prepare_response(response_data)

    def _error_response(self, error, status=400, code=None):
        """Respuesta de error estandarizada."""
        return self._prepare_response({
            'success': False,
            'error': error,
            'code': code or f'ERROR_{status}'
        }, status=status)

    def _format_user_data(self, user_data, detailed=False):
        """
        Formatea datos de usuario para respuesta API.
        
        Args:
            user_data (dict): Datos crudos del usuario
            detailed (bool): Si incluir datos relacionados expandidos
        """
        # Agregar alias user_id para claridad (usado en hotel.booking.user_id)
        if 'id' in user_data:
            user_data['user_id'] = user_data['id']  # Alias para uso en reservas
        
        # Formatear empresa
        if user_data.get('company_id'):
            user_data['company'] = {
                'id': user_data['company_id'][0],
                'name': user_data['company_id'][1]
            }
            del user_data['company_id']
        
        # Formatear estado/provincia
        if user_data.get('state_id'):
            user_data['state'] = {
                'id': user_data['state_id'][0],
                'name': user_data['state_id'][1]
            }
            del user_data['state_id']
        
        # Formatear país
        if user_data.get('country_id'):
            user_data['country'] = {
                'id': user_data['country_id'][0],
                'name': user_data['country_id'][1]
            }
            del user_data['country_id']
        
        # Formatear grupos (solo en vista detallada)
        if detailed and user_data.get('groups_id'):
            groups = request.env['res.groups'].browse(user_data['groups_id'])
            user_data['groups'] = [
                {'id': group.id, 'name': group.name, 'category': group.category_id.name if group.category_id else None}
                for group in groups
            ]
            del user_data['groups_id']
        
        # Formatear partner (solo en vista detallada)
        if detailed and user_data.get('partner_id'):
            user_data['partner'] = {
                'id': user_data['partner_id'][0],
                'name': user_data['partner_id'][1]
            }
            del user_data['partner_id']
        
        # Formatear título
        if detailed and user_data.get('title'):
            user_data['title'] = {
                'id': user_data['title'][0],
                'name': user_data['title'][1]
            }
        
        return user_data

    def _build_search_domain(self, params):
        """
        Construye dominio de búsqueda desde parámetros.
        
        Args:
            params (dict): Parámetros de búsqueda
            
        Returns:
            list: Dominio de búsqueda de Odoo
        """
        domain = []
        
        # Filtro de activos (por defecto solo activos)
        include_archived = params.get('include_archived', 'false').lower() == 'true'
        if not include_archived:
            domain.append(('active', '=', True))
        
        # Excluir usuarios del sistema (por defecto)
        exclude_system = params.get('exclude_system', 'true').lower() == 'true'
        if exclude_system:
            domain.append(('id', '!=', 1))  # Excluir usuario admin del sistema
        
        # Búsqueda por nombre, login o email
        search_term = params.get('search', '').strip()
        if search_term:
            domain.append('|')
            domain.append('|')
            domain.append(('name', 'ilike', search_term))
            domain.append(('login', 'ilike', search_term))
            domain.append(('email', 'ilike', search_term))
        
        # Filtros específicos
        if params.get('name'):
            domain.append(('name', 'ilike', params['name'].strip()))
        
        if params.get('login'):
            domain.append(('login', 'ilike', params['login'].strip()))
        
        if params.get('email'):
            domain.append(('email', 'ilike', params['email'].strip()))
        
        if params.get('phone'):
            phone_term = params['phone'].strip()
            domain.append('|')
            domain.append(('phone', 'ilike', phone_term))
            domain.append(('mobile', 'ilike', phone_term))
        
        # Filtro por empresa
        if params.get('company_id'):
            domain.append(('company_id', '=', int(params['company_id'])))
        
        # Filtro por grupos
        if params.get('group_id'):
            group_ids = [int(gid) for gid in params['group_id'].split(',')]
            domain.append(('groups_id', 'in', group_ids))
        
        return domain

    def _get_pagination_params(self, params):
        """Extrae y valida parámetros de paginación."""
        try:
            limit = min(int(params.get('limit', 50)), 1000)  # Máximo 1000
            offset = max(int(params.get('offset', 0)), 0)
            return limit, offset
        except ValueError:
            raise ValidationError('Los parámetros limit y offset deben ser números enteros')

    @http.route('/api/v1/responsables', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_responsables(self, **params):
        """
        Lista responsables (usuarios) con filtros y paginación.
        
        Query Parameters:
            - search: Búsqueda general en nombre, login y email
            - name: Filtro por nombre (parcial)
            - login: Filtro por login (parcial)
            - email: Filtro por email (parcial)
            - phone: Filtro por teléfono (parcial)
            - company_id: ID de la empresa
            - group_id: IDs de grupos separados por coma
            - include_archived: Incluir usuarios archivados (true/false)
            - exclude_system: Excluir usuarios del sistema (true/false, default: true)
            - limit: Límite de resultados (default: 50, max: 1000)
            - offset: Offset para paginación (default: 0)
            - order: Campo de ordenamiento (default: name)
        
        Returns:
            JSON con lista paginada de responsables
        """
        # Validar y obtener parámetros
        limit, offset = self._get_pagination_params(params)
        order = params.get('order', 'name')
        
        # Construir dominio de búsqueda
        domain = self._build_search_domain(params)
        
        # Verificar permisos antes de buscar
        User = request.env['res.users']
        try:
            User.check_access_rights('read', raise_exception=True)
            responsables = User.search_read(
                domain,
                self.FIELDS_LIST,
                limit=limit,
                offset=offset,
                order=order
            )
            
            # Verificar reglas de acceso para cada usuario
            if responsables:
                User.browse([r['id'] for r in responsables]).check_access_rule('read')
            
            # Contar total
            total_count = User.search_count(domain)
        except AccessError as e:
            _logger.warning(f"Error de acceso en get_responsables: {str(e)}")
            return self._error_response(
                'No tiene permisos para acceder a los responsables',
                status=403
            )
        
        # Formatear datos
        formatted_responsables = [
            self._format_user_data(responsable) for responsable in responsables
        ]
        
        _logger.info(
            f"API: Recuperados {len(responsables)} responsables (total: {total_count})"
        )
        
        return self._success_response(
            formatted_responsables,
            count=len(responsables),
            total_count=total_count,
            offset=offset,
            limit=limit,
            has_more=offset + len(responsables) < total_count
        )

    @http.route('/api/v1/responsables/<int:user_id>', auth='public', type='http', 
                methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_responsable_detail(self, user_id, **params):
        """
        Obtiene detalle completo de un responsable.
        
        Args:
            user_id: ID del usuario/responsable
            
        Query Parameters:
            - include_archived: Incluir si está archivado (true/false)
            
        Returns:
            JSON con datos completos del responsable
        """
        if user_id <= 0:
            return self._error_response('ID de responsable inválido', status=400)
        
        # Construir dominio
        domain = [('id', '=', user_id)]
        include_archived = params.get('include_archived', 'false').lower() == 'true'
        if not include_archived:
            domain.append(('active', '=', True))
        
        # Verificar permisos antes de buscar
        User = request.env['res.users']
        try:
            User.check_access_rights('read', raise_exception=True)
            responsable = User.search_read(
                domain,
                self.FIELDS_DETAIL,
                limit=1
            )
            
            if not responsable:
                _logger.info(f"Responsable con ID {user_id} no encontrado")
                return self._error_response(
                    f'Responsable con ID {user_id} no encontrado',
                    status=404,
                    code='NOT_FOUND'
                )
            
            # Verificar reglas de acceso
            User.browse(responsable[0]['id']).check_access_rule('read')
        except AccessError as e:
            _logger.warning(f"Error de acceso en get_responsable_detail: {str(e)}")
            return self._error_response(
                'No tiene permisos para acceder a este responsable',
                status=403
            )
        
        # Formatear datos
        responsable_data = self._format_user_data(responsable[0], detailed=True)
        
        _logger.info(f"API: Responsable {user_id} recuperado exitosamente")
        
        return self._success_response(responsable_data)

    @http.route('/api/v1/responsables/search', auth='public', type='http', 
                methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def search_responsables(self, **params):
        """
        Búsqueda avanzada de responsables con múltiples filtros.
        
        Alias de /api/v1/responsables con los mismos parámetros.
        Mantenido por retrocompatibilidad.
        """
        return self.get_responsables(**params)

    @http.route('/api/v1/responsables/stats', auth='public', type='http', 
                methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_responsables_stats(self, **params):
        """
        Obtiene estadísticas de responsables.
        
        Returns:
            JSON con estadísticas generales
        """
        User = request.env['res.users']
        
        try:
            User.check_access_rights('read', raise_exception=True)
            
            stats = {
                'total_responsables': User.search_count([('active', '=', True), ('id', '!=', 1)]),
                'total_archived': User.search_count([('active', '=', False)]),
                'total_active': User.search_count([('active', '=', True)])
            }
        except AccessError as e:
            _logger.warning(f"Error de acceso en get_responsables_stats: {str(e)}")
            return self._error_response(
                'No tiene permisos para acceder a las estadísticas de responsables',
                status=403
            )
        
        return self._success_response(stats)

