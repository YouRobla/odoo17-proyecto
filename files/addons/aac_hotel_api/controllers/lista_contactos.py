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


class ContactsAPIController(http.Controller):
    """
    API REST para gestión de contactos (res.partner) en Odoo 17.
    """

    # Campos base para listados
    FIELDS_LIST = [
        'id', 'name', 'email', 'phone', 'mobile', 'website',
        'street', 'city', 'state_id', 'country_id', 'zip',
        'is_company', 'customer_rank', 'supplier_rank', 'image_128'
    ]

    # Campos completos para detalle
    FIELDS_DETAIL = FIELDS_LIST + [
        'street2', 'image_1920', 'parent_id', 'comment', 'vat',
        'category_id', 'child_ids', 'company_id', 'user_id',
        'function', 'title', 'lang', 'ref', 'active'
    ]

    def _prepare_response(self, data, status=200):
        return Response(
            json.dumps(data, default=json_default, ensure_ascii=False),
            status=status,
            content_type='application/json; charset=utf-8',
        )

    def _success_response(self, data, message=None, **kwargs):
        response_data = {'success': True, 'data': data}
        if message:
            response_data['message'] = message
        response_data.update(kwargs)
        return self._prepare_response(response_data)

    def _error_response(self, error, status=400, code=None):
        return self._prepare_response({
            'success': False,
            'error': error,
            'code': code or f'ERROR_{status}'
        }, status=status)

    def _build_search_domain(self, params):
        """Construye el dominio de búsqueda basado en parámetros HTTP."""
        domain = []
        
        # Filtro por estado activo/archivado
        include_archived = params.get('include_archived', 'false').lower() == 'true'
        if not include_archived:
            domain.append(('active', '=', True))

        # Búsqueda general (nombre, email, ref)
        search_term = params.get('search')
        if search_term:
            domain.append('|')
            domain.append('|')
            domain.append(('name', 'ilike', search_term))
            domain.append(('email', 'ilike', search_term))
            domain.append(('ref', 'ilike', search_term))

        # Filtros específicos
        if params.get('is_company'):
            is_company = params.get('is_company').lower() == 'true'
            domain.append(('is_company', '=', is_company))
        
        if params.get('country_id'):
            try:
                domain.append(('country_id', '=', int(params.get('country_id'))))
            except ValueError:
                pass

        if params.get('email'):
            domain.append(('email', 'ilike', params.get('email')))

        return domain

    def _format_partner_data(self, partner_data, detailed=False):
        """Formatea datos de contacto para respuesta API."""
        # Copiar para no mutar el original si viene de cache
        data = partner_data.copy()

        # Helper para formatear campos Many2one (tuplas id, nombre)
        def fmt_m2o(field_name):
            val = data.get(field_name)
            if val:
                data[field_name.replace('_id', '')] = {'id': val[0], 'name': val[1]}
                del data[field_name]

        fmt_m2o('state_id')
        
        # País con código extra si es detallado
        if data.get('country_id'):
            country_info = {
                'id': data['country_id'][0],
                'name': data['country_id'][1]
            }
            if detailed:
                country_obj = request.env['res.country'].browse(data['country_id'][0])
                country_info['code'] = country_obj.code
            data['country'] = country_info
            del data['country_id']

        fmt_m2o('parent_id')
        fmt_m2o('company_id')
        fmt_m2o('user_id')
        fmt_m2o('title')

        # Formatear categorías (Many2many)
        if detailed and data.get('category_id'):
            categories = request.env['res.partner.category'].browse(data['category_id'])
            data['categories'] = [{'id': cat.id, 'name': cat.name, 'color': cat.color} for cat in categories]
            del data['category_id']

        # Contador de hijos
        if 'child_ids' in data:
            data['children_count'] = len(data['child_ids'])
            if not detailed:
                del data['child_ids']
        
        return data

    @http.route('/api/v1/contacts', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_contacts(self, **params):
        """Obtiene lista de contactos paginada."""
        domain = self._build_search_domain(params)
        
        # Paginación
        try:
            limit = int(params.get('limit', 20))
            page = int(params.get('page', 1))
            offset = (page - 1) * limit
        except ValueError:
            limit, page, offset = 20, 1, 0

        Partner = request.env['res.partner']
        Partner.check_access_rights('read', raise_exception=True)
        
        # Búsqueda
        contact_ids = Partner.search(domain, limit=limit, offset=offset, order='name asc')
        total_count = Partner.search_count(domain)
        
        contacts_data = Partner.search_read(
            [('id', 'in', contact_ids.ids)], 
            self.FIELDS_LIST
        )
        
        formatted_contacts = [self._format_partner_data(c, detailed=False) for c in contacts_data]
        
        return self._success_response(
            formatted_contacts,
            meta={
                'total': total_count,
                'page': page,
                'limit': limit,
                'pages': (total_count + limit - 1) // limit
            }
        )

    @http.route('/api/v1/contacts/<int:contact_id>', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_contact_detail(self, contact_id, **params):
        """Obtiene detalle completo de un contacto."""
        if contact_id <= 0:
            return self._error_response('ID de contacto inválido', status=400)
        
        domain = [('id', '=', contact_id)]
        include_archived = params.get('include_archived', 'false').lower() == 'true'
        if not include_archived:
            domain.append(('active', '=', True))
        
        Partner = request.env['res.partner']
        Partner.check_access_rights('read', raise_exception=True)
        
        contact = Partner.search_read(domain, self.FIELDS_DETAIL, limit=1)
        
        if not contact:
            return self._error_response('Contacto no encontrado', status=404, code='NOT_FOUND')
            
        # Verificar reglas de registro (Record Rules) explícitamente
        try:
            Partner.browse(contact[0]['id']).check_access_rule('read')
        except AccessError:
            return self._error_response('No tiene permiso para ver este registro', status=403)
        
        contact_data = self._format_partner_data(contact[0], detailed=True)
        return self._success_response(contact_data)

    @http.route('/api/v1/contacts/search', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def search_contacts(self, **params):
        """Alias para búsqueda."""
        return self.get_contacts(**params)

    @http.route('/api/v1/contacts/stats', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def get_contacts_stats(self, **params):
        Partner = request.env['res.partner']
        Partner.check_access_rights('read', raise_exception=True)
        
        stats = {
            'total_contacts': Partner.search_count([('active', '=', True)]),
            'total_companies': Partner.search_count([('active', '=', True), ('is_company', '=', True)]),
            'total_individuals': Partner.search_count([('active', '=', True), ('is_company', '=', False)]),
            'total_customers': Partner.search_count([('active', '=', True), ('customer_rank', '>', 0)]),
            'total_suppliers': Partner.search_count([('active', '=', True), ('supplier_rank', '>', 0)]),
        }
        
        if params.get('include_country_stats', 'false').lower() == 'true':
            # Nota: read_group ha cambiado ligeramente en versiones recientes, pero esta sintaxis suele ser compatible
            # En Odoo 17 puro se prefiere _read_group pero read_group sigue existiendo.
            country_stats = Partner.read_group(
                [('active', '=', True), ('country_id', '!=', False)],
                ['country_id'],
                ['country_id'],
                limit=10,
                orderby='country_id_count DESC'
            )
            stats['top_countries'] = [
                {'country': s['country_id'][1], 'count': s['country_id_count']} 
                for s in country_stats
            ]
        
        return self._success_response(stats)

    @http.route('/api/v1/contacts/export', auth='public', type='http', methods=['GET'], csrf=False)
    @validate_api_key
    @handle_exceptions
    def export_contacts(self, **params):
        max_records = min(int(params.get('max_records', 5000)), 10000)
        domain = self._build_search_domain(params)
        
        Partner = request.env['res.partner']
        Partner.check_access_rights('read', raise_exception=True)
        
        total_count = Partner.search_count(domain)
        if total_count > max_records:
            return self._error_response(f'Demasiados registros ({total_count}). Use filtros.', status=400)
            
        contacts = Partner.search_read(domain, self.FIELDS_DETAIL, limit=max_records, order='name')
        
        formatted = [self._format_partner_data(c, detailed=True) for c in contacts]
        
        return self._success_response(
            formatted,
            total_exported=len(contacts),
            export_date=str(json_default(request.env.cr.now()))
        )