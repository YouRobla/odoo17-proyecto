# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


class ApiResponse(models.Model):
    _name = 'hotel.api.response'
    _description = 'API Response Helper'
    _transient = False  
    
    name = fields.Char('Referencia', default='API Response')
    request_date = fields.Datetime('Fecha de Solicitud', default=fields.Datetime.now)
    response_data = fields.Text('Datos de Respuesta')
    status_code = fields.Integer('Código de Estado')
    is_successful = fields.Boolean('Exitoso')
    
    @staticmethod
    def success(data=None, message="Operación exitosa", status_code=200, meta=None):

        response = {
            'success': True,
            'message': message,
            'status_code': status_code,
            'timestamp': datetime.now().isoformat()
        }
        
        if data is not None:
            response['data'] = data
            
        if meta:
            response['meta'] = meta
            
        _logger.info(f"API Success Response: {message} (Status: {status_code})")
        return response
    
    @staticmethod
    def error(message="Error en la operación", status_code=400, errors=None, 
              error_code=None, details=None):

        response = {
            'success': False,
            'message': message,
            'status_code': status_code,
            'timestamp': datetime.now().isoformat()
        }
        
        if error_code:
            response['error_code'] = error_code
            
        if errors:
            response['errors'] = errors if isinstance(errors, (list, dict)) else [errors]
            
        if details:
            response['details'] = details
            
        _logger.error(f"API Error Response: {message} (Status: {status_code}) - {errors}")
        return response
    
    @staticmethod
    def paginated(data, page=1, per_page=10, total=0, extra_meta=None):

        if not isinstance(page, int) or page < 1:
            page = 1
        if not isinstance(per_page, int) or per_page < 1:
            per_page = 10
        if not isinstance(total, int) or total < 0:
            total = 0
            
        total_pages = (total + per_page - 1) // per_page if total > 0 else 0
        has_next = page < total_pages
        has_prev = page > 1
        
        pagination_meta = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'total_pages': total_pages,
            'has_next': has_next,
            'has_prev': has_prev
        }
        
        if extra_meta:
            pagination_meta.update(extra_meta)
        
        return {
            'success': True,
            'data': data if isinstance(data, list) else [],
            'pagination': pagination_meta,
            'timestamp': datetime.now().isoformat()
        }
    
    @staticmethod
    def validation_error(errors, message="Errores de validación"):

        return ApiResponse.error(
            message=message,
            status_code=422,
            errors=errors,
            error_code='VALIDATION_ERROR'
        )
    
    @staticmethod
    def not_found(resource="Recurso", resource_id=None):

        message = f"{resource} no encontrado"
        if resource_id:
            message += f" (ID: {resource_id})"
            
        return ApiResponse.error(
            message=message,
            status_code=404,
            error_code='NOT_FOUND'
        )
    
    @staticmethod
    def unauthorized(message="No autorizado"):
        return ApiResponse.error(
            message=message,
            status_code=401,
            error_code='UNAUTHORIZED'
        )
    
    @staticmethod
    def forbidden(message="Acceso prohibido"):
        """Respuesta de acceso prohibido"""
        return ApiResponse.error(
            message=message,
            status_code=403,
            error_code='FORBIDDEN'
        )
    
    @staticmethod
    def created(data=None, message="Recurso creado exitosamente"):
        """Respuesta para creación exitosa"""
        return ApiResponse.success(
            data=data,
            message=message,
            status_code=201
        )
    
    @staticmethod
    def no_content(message="Operación exitosa sin contenido"):
        """Respuesta sin contenido"""
        return ApiResponse.success(
            message=message,
            status_code=204
        )
    
    @api.model
    def log_response(self, response_data, request_info=None):

        try:
            self.create({
                'name': f"API Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                'response_data': str(response_data),
                'status_code': response_data.get('status_code', 0),
                'is_successful': response_data.get('success', False),
            })
        except Exception as e:
            _logger.warning(f"No se pudo guardar log de API: {str(e)}")
    
    @staticmethod
    def handle_exception(exception):
        if isinstance(exception, ValidationError):
            return ApiResponse.validation_error(
                errors={'validation': str(exception)},
                message="Error de validación"
            )
        
        _logger.exception("Error no controlado en API")
        return ApiResponse.error(
            message="Error interno del servidor",
            status_code=500,
            error_code='INTERNAL_ERROR',
            details=str(exception) if hasattr(exception, '__str__') else None
        )