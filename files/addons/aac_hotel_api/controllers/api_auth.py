# -*- coding: utf-8 -*-
import json
import logging
from functools import wraps
from odoo import http
from odoo.http import request, Response
from odoo.tools import json_default

_logger = logging.getLogger(__name__)


def validate_api_key(func):
    """
    Decorador para validar API Key nativa de Odoo en endpoints.
    
    Usa el sistema nativo de API keys de Odoo 17 que se genera desde:
    Preferencias del usuario → Seguridad de la cuenta → Claves API
    
    La API key debe venir en el header 'X-API-Key' o 'Authorization: Bearer <key>'
    Si la validación es exitosa, establece el usuario correspondiente en request.env.
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        # Obtener API key del header
        api_key = None
        
        # Intentar obtener de X-API-Key header
        if hasattr(request.httprequest, 'headers'):
            api_key = request.httprequest.headers.get('X-API-Key') or \
                     request.httprequest.headers.get('x-api-key')
        
        # Si no está en X-API-Key, intentar Authorization Bearer
        if not api_key and hasattr(request.httprequest, 'headers'):
            auth_header = request.httprequest.headers.get('Authorization') or \
                         request.httprequest.headers.get('authorization')
            if auth_header and auth_header.startswith('Bearer '):
                api_key = auth_header.replace('Bearer ', '').strip()
        
        # Si aún no hay API key, intentar desde parámetros (solo para GET/OPTIONS)
        if not api_key and request.httprequest.method in ('GET', 'OPTIONS'):
            api_key = request.params.get('api_key') or request.httprequest.args.get('api_key')
        
        if not api_key:
            _logger.warning(
                "Intento de acceso sin API key a endpoint: %s",
                func.__name__
            )
            return Response(
                json.dumps({
                    'success': False,
                    'error': 'API Key requerida. Proporcione la API key en el header X-API-Key o Authorization: Bearer <key>. Puede generarla desde Preferencias → Seguridad de la cuenta → Claves API'
                }, default=json_default),
                status=401,
                content_type='application/json',
                headers={
                    'WWW-Authenticate': 'Bearer'
                }
            )
        
        # Usar el sistema nativo de autenticación de Odoo 17
        # Las API keys nativas se generan desde: Preferencias → Seguridad de la cuenta → Claves API
        uid = None
        
        try:
            # Odoo 17 almacena las API keys en res.users.apikeys
            # Usar el método nativo _check_credentials para validar
            apikey_model = request.env['res.users.apikeys'].sudo()
            
            # El método _check_credentials verifica y retorna el user_id
            uid = apikey_model._check_credentials(scope='rpc', key=api_key)
            
            if uid:
                user = request.env['res.users'].sudo().browse(uid)
                _logger.debug("API key nativa validada para usuario: %s", user.login)
                
        except (KeyError, AttributeError, ValueError) as e:
            _logger.debug("Error validando API key nativa: %s", str(e))
        
        # Si aún no hay uid, la API key es inválida
        if not uid:
            _logger.warning(
                "API key inválida o expirada en endpoint: %s (IP: %s)",
                func.__name__,
                getattr(request.httprequest, 'remote_addr', 'unknown')
            )
            return Response(
                json.dumps({
                    'success': False,
                    'error': 'API Key inválida, expirada o revocada. Verifique su API key en Preferencias → Seguridad de la cuenta → Claves API'
                }, default=json_default),
                status=401,
                content_type='application/json',
                headers={
                    'WWW-Authenticate': 'Bearer'
                }
            )
        
        # Establecer el usuario en el entorno
        user = request.env['res.users'].sudo().browse(uid)
        if not user.exists():
            return Response(
                json.dumps({
                    'success': False,
                    'error': 'Usuario asociado a la API key no encontrado'
                }, default=json_default),
                status=401,
                content_type='application/json',
                headers={
                    'WWW-Authenticate': 'Bearer'
                }
            )
        
        # Actualizar el entorno completo con el usuario autenticado
        request.update_env(user=uid)
        
        _logger.debug(
            "API key validada exitosamente para usuario %s en endpoint: %s",
            user.login,
            func.__name__
        )
        
        # Ejecutar la función original con el usuario correcto
        return func(self, *args, **kwargs)
    
    return wrapper


class ApiKeyController(http.Controller):
    """Controlador para gestión de API Keys"""

    def _prepare_response(self, data, status=200):
        """Preparar respuesta HTTP con formato JSON"""
        return Response(
            json.dumps(data, default=json_default),
            status=status,
            content_type='application/json'
        )

    @http.route('/api/auth/generate_key', auth='public', type='http', methods=['POST'], csrf=False)
    def generate_api_key(self, **kw):
        """
        Generar una nueva API key nativa de Odoo para el usuario autenticado.
        
        Endpoint: POST /api/auth/generate_key
        
        Body (JSON):
        {
            "name": "React Frontend",  // requerido
            "scope": "{'userinfo': ['res.partner', 'read']}"  // opcional, alcance de la API key
        }
        
        Returns:
            JSON con la API key generada (mostrada solo una vez)
        """
        try:
            data = json.loads(request.httprequest.data.decode('utf-8')) if request.httprequest.data else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        
        name = data.get('name') or kw.get('name')
        if not name:
            return self._prepare_response({
                'success': False,
                'error': 'El campo "name" es requerido'
            }, status=400)
        
        try:
            # Usar el sistema nativo de API keys de Odoo 17
            apikey_sudo = request.env['res.users.apikeys'].sudo()
            
            # El scope es opcional en Odoo 17
            scope = data.get('scope') or kw.get('scope')
            
            # Usar el método nativo _generate de Odoo que crea la key de forma segura
            # Este método automáticamente usa request.env.user.id como user_id
            plaintext_key = apikey_sudo._generate(
                scope=scope,
                name=name
            )
            
            _logger.info(
                "API key nativa generada para usuario %s: %s",
                request.env.user.login,
                name
            )
            
            return self._prepare_response({
                'success': True,
                'message': 'API key generada exitosamente',
                'data': {
                    'name': name,
                    'api_key': plaintext_key,  # Solo se muestra una vez
                    'user_id': request.env.user.id,
                    'user_login': request.env.user.login,
                    'warning': 'Guarde esta API key de forma segura. No podrá verla nuevamente.'
                }
            }, status=201)
            
        except (KeyError, AttributeError, ValueError, TypeError) as e:
            _logger.error("Error al generar API key nativa: %s", str(e))
            return self._prepare_response({
                'success': False,
                'error': f'Error al generar API key: {str(e)}'
            }, status=500)

    @http.route('/api/auth/my_keys', auth='public', type='http', methods=['GET'], csrf=False)
    def get_my_api_keys(self, **_kw):
        """
        Obtener lista de API keys nativas del usuario autenticado (sin mostrar las keys).
        
        Endpoint: GET /api/auth/my_keys
        """
        api_keys = request.env['res.users.apikeys'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ], order='create_date desc')
        
        keys_data = []
        for key in api_keys:
            keys_data.append({
                'id': key.id,
                'name': key.name,
                'created_at': key.create_date.isoformat() if key.create_date else None,
                'scope': key.scope if hasattr(key, 'scope') else None,
            })
        
        return self._prepare_response({
            'success': True,
            'count': len(keys_data),
            'data': keys_data
        })

    @http.route('/api/auth/revoke_key/<int:key_id>', auth='public', type='http', methods=['POST', 'DELETE'], csrf=False)
    def revoke_api_key(self, key_id, **_kw):
        """
        Revocar (eliminar) una API key nativa del usuario autenticado.
        
        Endpoint: POST/DELETE /api/auth/revoke_key/<key_id>
        """
        api_key_record = request.env['res.users.apikeys'].sudo().browse(key_id)
        
        if not api_key_record.exists():
            return self._prepare_response({
                'success': False,
                'error': f'API key con ID {key_id} no encontrada'
            }, status=404)
        
        # Verificar que el usuario sea el propietario
        if api_key_record.user_id.id != request.env.user.id:
            return self._prepare_response({
                'success': False,
                'error': 'No tiene permisos para revocar esta API key'
            }, status=403)
        
        key_name = api_key_record.name
        
        # Eliminar la API key (el sistema nativo de Odoo no tiene método revoke, se elimina)
        api_key_record.unlink()
        
        _logger.info(
            "API key revocada/eliminada por usuario %s: %s (%s)",
            request.env.user.login,
            key_name,
            key_id
        )
        
        return self._prepare_response({
            'success': True,
            'message': f'API key "{key_name}" revocada exitosamente'
        })

    @http.route('/api/auth/validate', auth='public', type='http', methods=['POST'], csrf=False)
    def validate_api_key_public(self, **kw):
        """
        Endpoint PÚBLICO para validar una API key desde el frontend.
        
        Endpoint: POST /api/auth/validate
        
        Body (JSON):
        {
            "api_key": "la_key_a_validar"
        }
        
        Returns:
            JSON con resultado de validación
        """
        try:
            data = json.loads(request.httprequest.data.decode('utf-8')) if request.httprequest.data else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        
        api_key = data.get('api_key') or kw.get('api_key')
        
        if not api_key:
            return self._prepare_response({
                'success': False,
                'valid': False,
                'error': 'Debe proporcionar la API key a validar'
            }, status=400)
        
        try:
            # Usar el método nativo _check_credentials para validar
            apikey_model = request.env['res.users.apikeys'].sudo()
            
            # El método _check_credentials verifica y retorna el user_id
            user_id = apikey_model._check_credentials(scope='rpc', key=api_key)
            
            if not user_id:
                _logger.warning("Intento de validación con API key inválida")
                return self._prepare_response({
                    'success': False,
                    'valid': False,
                    'message': 'API key inválida o revocada'
                })
            
            user = request.env['res.users'].sudo().browse(user_id)
            
            _logger.info("API key validada exitosamente para usuario: %s", user.login)
            
            return self._prepare_response({
                'success': True,
                'valid': True,
                'message': 'API key válida',
                'data': {
                    'user_name': user.name,
                    'user_login': user.login,
                }
            })
            
        except (KeyError, AttributeError, ValueError, TypeError) as e:
            _logger.error("Error al validar API key: %s", str(e))
            return self._prepare_response({
                'success': False,
                'valid': False,
                'error': 'Error al validar API key'
            }, status=500)

    @http.route('/api/auth/test_key', auth='public', type='http', methods=['GET', 'POST'], csrf=False)
    def test_api_key(self, **kw):
        """
        Probar una API key nativa (validar sin crear).
        Solo para usuarios autenticados.
        
        Endpoint: GET/POST /api/auth/test_key
        
        Query/Body:
            api_key: La API key a probar
        """
        api_key = kw.get('api_key')
        if not api_key:
            try:
                data = json.loads(request.httprequest.data.decode('utf-8')) if request.httprequest.data else {}
                api_key = data.get('api_key')
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                api_key = None
        
        if not api_key:
            return self._prepare_response({
                'success': False,
                'error': 'Debe proporcionar la API key a probar'
            }, status=400)
        
        try:
            # Usar el método nativo _check_credentials para validar
            apikey_model = request.env['res.users.apikeys'].sudo()
            
            # El método _check_credentials verifica y retorna el user_id
            user_id = apikey_model._check_credentials(scope='rpc', key=api_key)
            
            if not user_id:
                return self._prepare_response({
                    'success': False,
                    'valid': False,
                    'error': 'API key inválida o revocada'
                })
            
            user = request.env['res.users'].sudo().browse(user_id)
            
            return self._prepare_response({
                'success': True,
                'valid': True,
                'data': {
                    'user_id': user.id,
                    'user_name': user.name,
                    'user_login': user.login,
                }
            })
            
        except (KeyError, AttributeError, ValueError, TypeError) as e:
            _logger.error("Error al probar API key: %s", str(e))
            return self._prepare_response({
                'success': False,
                'valid': False,
                'error': f'Error al validar API key: {str(e)}'
            }, status=500)

