# -*- coding: utf-8 -*-
import json
import logging
from datetime import datetime
from odoo import http, _
from odoo.http import request, Response
from odoo.tools import json_default
from odoo.exceptions import ValidationError, AccessError, UserError
from .api_auth import validate_api_key

_logger = logging.getLogger(__name__)


class HotelCambioPrecioController(http.Controller):
    """Controlador REST API para gestión de cambios de precio en líneas de reserva"""

    # =============================================================================
    # UTILIDADES PRIVADAS
    # =============================================================================

    def _prepare_response(self, data=None, message=None, error=None, status=200):
        """
        Preparar respuesta JSON estandarizada
        
        Args:
            data: Datos a retornar
            message: Mensaje de éxito
            error: Mensaje de error
            status: Código de estado HTTP
        """
        response_data = {
            'success': status < 400,
            'timestamp': datetime.now().isoformat(),
        }
        
        if data is not None:
            response_data['data'] = data
        if message:
            response_data['message'] = message
        if error:
            response_data['error'] = error
        
        return Response(
            json.dumps(response_data, default=json_default),
            status=status,
            content_type='application/json'
        )

    def _get_request_data(self):
        """Extraer y validar datos JSON del request"""
        try:
            if request.httprequest.data:
                return json.loads(request.httprequest.data.decode('utf-8'))
            return {}
        except json.JSONDecodeError as e:
            raise ValidationError(_('JSON inválido: %s') % str(e))

    def _check_booking_line_access(self, line_id):
        """
        Verificar existencia y acceso a la línea de reserva
        
        Returns:
            hotel.booking.line: Registro encontrado
        Raises:
            ValidationError: Si no existe o no hay acceso
        """
        booking_line = request.env['hotel.booking.line'].browse(line_id)
        
        if not booking_line.exists():
            raise ValidationError(_('Línea de reserva con ID %s no encontrada') % line_id)
        
        # Verificar permisos de lectura
        try:
            booking_line.check_access_rights('read')
            booking_line.check_access_rule('read')
        except AccessError:
            raise AccessError(_('No tiene permisos para acceder a esta línea de reserva'))
        
        return booking_line

    def _validate_price_change_permissions(self, booking_line):
        """Validar permisos para cambio de precio"""
        # Verificar permisos de escritura
        try:
            booking_line.check_access_rights('write')
            booking_line.check_access_rule('write')
        except AccessError:
            raise AccessError(_('No tiene permisos para modificar precios'))
        
        # Verificar que la reserva pueda ser modificada según su estado
        terminal_states = ['cancelled', 'no_show', 'checkout']
        if booking_line.booking_id.status_bar in terminal_states:
            raise ValidationError(
                _('No se puede modificar el precio de una reserva en estado "%s"') 
                % booking_line.booking_id.status_bar
            )
        
        # Verificar que la reserva tenga un estado válido para cambios
        valid_states = ['initial', 'draft', 'confirmed', 'checkin', 'allot', 'room_ready']
        if booking_line.booking_id.status_bar not in valid_states:
            raise ValidationError(
                _('No se puede modificar el precio en el estado actual "%s"') 
                % booking_line.booking_id.status_bar
            )

    def _validate_price_data(self, data):
        """Validar datos de precio"""
        # Validar campos requeridos
        if 'new_price' not in data:
            raise ValidationError(_('El campo "new_price" es requerido'))
        
        if 'reason' not in data or not data['reason'].strip():
            raise ValidationError(_('El campo "reason" es requerido'))
        
        # Validar nuevo precio
        try:
            new_price = float(data['new_price'])
        except (ValueError, TypeError):
            raise ValidationError(_('El precio debe ser un número válido'))
        
        if new_price < 0:
            raise ValidationError(_('El precio no puede ser negativo'))
        
        if new_price > 999999.99:
            raise ValidationError(_('El precio no puede ser mayor a 999,999.99'))
        
        # Validar razón del cambio
        reason = data['reason'].strip()
        if len(reason) < 3:
            raise ValidationError(_('La razón del cambio debe tener al menos 3 caracteres'))
        
        if len(reason) > 500:
            raise ValidationError(_('La razón del cambio no puede exceder 500 caracteres'))
        
        return new_price, reason

    def _validate_price_change_business_rules(self, booking_line, new_price, reason):
        """Validar reglas de negocio para cambio de precio"""
        current_price = booking_line.price or 0
        
        # Validar cambio significativo (opcional) - solo si hay precio actual
        if current_price > 0:
            price_difference = abs(new_price - current_price)
            if price_difference < 0.01 and not booking_line.env.context.get('force_price_change'):
                raise ValidationError(
                    _('El cambio de precio debe ser significativo (mínimo 0.01). Use "force": true para forzar cambios menores')
                )
        
        # Validar límites de descuento (máximo 100% de descuento) - solo si hay precio de referencia
        original_price = booking_line.original_price or current_price
        if original_price > 0 and new_price < original_price:
            discount_percentage = ((original_price - new_price) / original_price) * 100
            if discount_percentage > 100:
                raise ValidationError(
                    _('No se puede aplicar un descuento mayor al 100%% del precio original')
                )
        
        # Validar que el precio no sea excesivamente alto - solo si hay precio de referencia
        if original_price > 0 and new_price > original_price * 3:
            raise ValidationError(
                _('El nuevo precio no puede ser más de 3 veces el precio original')
            )
        
        # Validar que la reserva tenga fechas válidas
        if not booking_line.booking_id.check_in or not booking_line.booking_id.check_out:
            raise ValidationError(
                _('No se puede cambiar el precio de una reserva sin fechas de check-in y check-out')
            )
        
        # Validar que la reserva tenga al menos un huésped
        if not booking_line.guest_info_ids:
            raise ValidationError(
                _('No se puede cambiar el precio de una línea sin huéspedes asignados')
            )

    def _validate_booking_line_integrity(self, booking_line):
        """Validar integridad de la línea de reserva"""
        # Verificar que la línea tenga un producto válido
        if not booking_line.product_id:
            raise ValidationError(_('La línea de reserva debe tener un producto asignado'))
        
        # Verificar que el producto sea una habitación
        if not booking_line.product_id.is_room_type:
            raise ValidationError(_('El producto debe ser un tipo de habitación'))
        
        # Verificar que la línea tenga una reserva válida
        if not booking_line.booking_id:
            raise ValidationError(_('La línea de reserva debe estar asociada a una reserva'))
        
        # Verificar que la reserva tenga un cliente
        if not booking_line.booking_id.partner_id:
            raise ValidationError(_('La reserva debe tener un cliente asignado'))
        
        # Verificar que la línea tenga días de reserva válidos
        if not booking_line.booking_days or booking_line.booking_days <= 0:
            raise ValidationError(_('La línea de reserva debe tener días de reserva válidos'))

    def _validate_currency_consistency(self, booking_line, new_price):
        """Validar consistencia de moneda"""
        if not booking_line.currency_id:
            raise ValidationError(_('La línea de reserva debe tener una moneda asignada'))
        
        # Verificar que la moneda esté activa
        if not booking_line.currency_id.active:
            raise ValidationError(_('La moneda asignada no está activa'))
        
        # Verificar que el precio sea válido para la moneda
        currency = booking_line.currency_id
        if currency.name == 'PEN' and new_price > 1000000:
            raise ValidationError(_('El precio no puede exceder 1,000,000 PEN'))
        elif currency.name == 'USD' and new_price > 300000:
            raise ValidationError(_('El precio no puede exceder 300,000 USD'))
        elif currency.name == 'EUR' and new_price > 300000:
            raise ValidationError(_('El precio no puede exceder 300,000 EUR'))

    def _validate_user_permissions(self, booking_line):
        """Validar permisos específicos del usuario"""
        user = request.env.user
        
        # Verificar que el usuario tenga permisos de hotel
        if not (user.has_group('base.group_system') or 
                user.has_group('base.group_erp_manager')):
            # Si no es administrador, verificar que sea responsable de la reserva
            if booking_line.booking_id.user_id != user:
                raise AccessError(_('Solo el responsable de la reserva puede cambiar precios'))
        
        # Nota: Se eliminó la validación de "modo demo" ya que base.group_no_one
        # es un grupo técnico interno y no indica modo demo

    def _validate_booking_line_state(self, booking_line):
        """Validar estado de la línea de reserva"""
        # Verificar que la línea no esté en un estado que impida cambios
        if hasattr(booking_line, 'state') and booking_line.state in ['cancelled', 'done']:
            raise ValidationError(_('No se puede cambiar el precio de una línea en estado "%s"') % booking_line.state)
        
        # Verificar que la línea tenga un precio definido (puede ser 0 en cambios de habitación)
        # Solo validar que el campo price no sea None
        if booking_line.price is None:
            raise ValidationError(_('La línea de reserva debe tener un campo de precio definido'))
        
        # Verificar que la línea tenga días de reserva válidos
        if not booking_line.booking_days or booking_line.booking_days <= 0:
            raise ValidationError(_('La línea de reserva debe tener días de reserva válidos'))

    def _calculate_discount_info(self, original_price, current_price):
        """Calcular información de descuento"""
        discount_percentage = 0
        discount_amount = 0
        
        if original_price and original_price > 0:
            discount_amount = original_price - current_price
            discount_percentage = (discount_amount / original_price) * 100
        
        return {
            'discount_percentage': round(discount_percentage, 2),
            'discount_amount': round(discount_amount, 2)
        }

    def _format_price_info(self, booking_line):
        """Formatear información de precios de una línea"""
        original_price = booking_line.original_price or booking_line.price
        discount_info = self._calculate_discount_info(original_price, booking_line.price)
        
        return {
            'booking_line_id': booking_line.id,
            'booking_sequence_id': booking_line.booking_sequence_id,
            'booking_id': booking_line.booking_id.id,
            'room_name': booking_line.product_id.name,
            'room_code': booking_line.product_id.default_code or '',
            'original_price': float(original_price),
            'current_price': float(booking_line.price),
            'discount_percentage': discount_info['discount_percentage'],
            'discount_amount': discount_info['discount_amount'],
            'discount_reason': booking_line.discount_reason or '',
            'currency': {
                'id': booking_line.currency_id.id,
                'name': booking_line.currency_id.name,
                'symbol': booking_line.currency_id.symbol,
            },
            'booking_days': booking_line.booking_days,
            'subtotal_price': float(booking_line.subtotal_price),
            'taxed_price': float(booking_line.taxed_price),
            'checkin': booking_line.booking_id.check_in.isoformat() if booking_line.booking_id.check_in else None,
            'checkout': booking_line.booking_id.check_out.isoformat() if booking_line.booking_id.check_out else None,
            'state': booking_line.booking_id.status_bar,
        }

    # =============================================================================
    # ENDPOINTS PARA CONSULTA DE INFORMACIÓN
    # =============================================================================

    @http.route(
        '/api/hotel/booking_line/<int:line_id>/price_info',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False
    )
    @validate_api_key
    def get_price_info(self, line_id, **kw):
        """
        Obtener información detallada de precios de una línea de reserva
        
        Args:
            line_id: ID de la línea de reserva
            
        Returns:
            JSON con información de precios, descuentos y estado actual
        """
        try:
            booking_line = self._check_booking_line_access(line_id)
            price_info = self._format_price_info(booking_line)
            
            _logger.info('Información de precios obtenida para línea %s', line_id)
            
            return self._prepare_response(
                data=price_info,
                message=_('Información obtenida exitosamente')
            )
            
        except (ValidationError, AccessError) as e:
            _logger.warning('Error de acceso en get_price_info: %s', str(e))
            return self._prepare_response(error=str(e), status=403)
            
        except Exception as e:
            _logger.exception('Error inesperado en get_price_info: %s', str(e))
            return self._prepare_response(
                error=_('Error interno del servidor'),
                status=500
            )

    @http.route(
        '/api/hotel/booking_line/<int:line_id>/price_history',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False
    )
    @validate_api_key
    def get_price_history(self, line_id, **kw):
        """
        Obtener historial de cambios de precio
        
        Args:
            line_id: ID de la línea de reserva
            
        Returns:
            JSON con historial de cambios de precio
        """
        try:
            booking_line = self._check_booking_line_access(line_id)
            
            # Obtener mensajes de auditoría relacionados con cambios de precio
            # Verificar permisos antes de buscar mensajes
            try:
                request.env['mail.message'].check_access_rights('read', raise_exception=True)
                messages = request.env['mail.message'].search([
                    ('model', '=', 'hotel.booking.line'),
                    ('res_id', '=', line_id),
                    '|',
                    ('body', 'ilike', 'price'),
                    ('body', 'ilike', 'precio'),
                ], order='date desc', limit=20)
                messages.check_access_rule('read')
            except AccessError:
                # Si no tiene permisos directos, solo mostrar información de la línea
                messages = request.env['mail.message']
            
            history_entries = []
            for msg in messages:
                history_entries.append({
                    'date': msg.date.isoformat(),
                    'public': msg.author_id.name if msg.author_id else 'Sistema',
                    'description': msg.body,
                })
            
            history = {
                'booking_line_info': self._format_price_info(booking_line),
                'changes': history_entries,
                'last_update': booking_line.write_date.isoformat() if booking_line.write_date else None,
            }
            
            _logger.info('Historial de precios obtenido para línea %s', line_id)
            
            return self._prepare_response(
                data=history,
                message=_('Historial obtenido exitosamente')
            )
            
        except (ValidationError, AccessError) as e:
            _logger.warning('Error de acceso en get_price_history: %s', str(e))
            return self._prepare_response(error=str(e), status=403)
            
        except Exception as e:
            _logger.exception('Error inesperado en get_price_history: %s', str(e))
            return self._prepare_response(
                error=_('Error interno del servidor'),
                status=500
            )

    # =============================================================================
    # ENDPOINTS PARA MODIFICACIÓN DE PRECIOS
    # =============================================================================

    @http.route(
        '/api/hotel/booking_line/<int:line_id>/change_price',
        auth='public',
        type='http',
        methods=['POST'],
        csrf=False
    )
    @validate_api_key
    def change_price(self, line_id, **kw):
        """
        Cambiar precio de una línea de reserva con validaciones completas
        
        Args:
            line_id: ID de la línea de reserva
            
        Body JSON:
            {
                "new_price": float (requerido),
                "reason": str (requerido),
                "force": bool (opcional, default: false)
            }
            
        Returns:
            JSON con información del cambio realizado
        """
        try:
            # Validar acceso y obtener línea
            booking_line = self._check_booking_line_access(line_id)
            
            # Validaciones completas
            try:
                # Validar permisos de cambio de precio
                _logger.debug('Validando permisos de cambio de precio para línea %s', line_id)
                self._validate_price_change_permissions(booking_line)
                
                # Validar integridad de la línea
                _logger.debug('Validando integridad de la línea %s', line_id)
                self._validate_booking_line_integrity(booking_line)
                
                # Validar estado de la línea
                _logger.debug('Validando estado de la línea %s', line_id)
                self._validate_booking_line_state(booking_line)
                
                # Validar permisos del usuario
                _logger.debug('Validando permisos del usuario para línea %s', line_id)
                self._validate_user_permissions(booking_line)
                
            except (ValidationError, AccessError) as e:
                _logger.warning('Error de validación en change_price (permisos/integridad): %s', str(e))
                return self._prepare_response(error=str(e), status=400)
            
            # Obtener y validar datos del request
            _logger.debug('Obteniendo datos del request para línea %s', line_id)
            data = self._get_request_data()
            _logger.debug('Datos recibidos: %s', data)
            
            # Validar datos de precio
            try:
                _logger.debug('Validando datos de precio para línea %s', line_id)
                new_price, reason = self._validate_price_data(data)
                _logger.debug('Precio validado: %s, Razón: %s', new_price, reason)
            except ValidationError as e:
                _logger.warning('Error validando datos de precio: %s', str(e))
                return self._prepare_response(error=str(e), status=400)
            
            # Validar reglas de negocio
            try:
                _logger.debug('Validando reglas de negocio para línea %s', line_id)
                self._validate_price_change_business_rules(booking_line, new_price, reason)
                
                # Validar consistencia de moneda
                _logger.debug('Validando consistencia de moneda para línea %s', line_id)
                self._validate_currency_consistency(booking_line, new_price)
                
            except ValidationError as e:
                _logger.warning('Error validando reglas de negocio/moneda: %s', str(e))
                return self._prepare_response(error=str(e), status=400)
            
            # Guardar precio actual para el log
            old_price = booking_line.price
            original_price = booking_line.original_price or old_price
            
            # Preparar valores de actualización
            update_vals = {
                'price': new_price,
                'discount_reason': reason,
            }
            
            # Establecer precio original si no existe
            if not booking_line.original_price:
                update_vals['original_price'] = old_price
                original_price = old_price
            
            # NO establecer el campo discount porque el precio (new_price) ya es el precio final por noche
            # El descuento se calcula automáticamente como diferencia entre original_price y new_price
            # No aplicar descuento adicional en el cálculo del subtotal
            
            # Actualizar en el contexto de un entorno transaccional
            with request.env.cr.savepoint():
                booking_line.write(update_vals)
                
                # Registrar cambio en el chatter
                message_body = _(
                    '<p><strong>Cambio de precio realizado</strong></p>'
                    '<ul>'
                    '<li>Precio anterior: %s %s</li>'
                    '<li>Precio nuevo: %s %s</li>'
                    '<li>Motivo: %s</li>'
                    '<li>Usuario: %s</li>'
                    '</ul>'
                ) % (
                    booking_line.currency_id.symbol,
                    old_price,
                    booking_line.currency_id.symbol,
                    new_price,
                    reason,
                    request.env.user.name
                )
                
                booking_line.booking_id.message_post(
                    body=message_body,
                    subject=_('Cambio de precio - Línea %s') % booking_line.booking_sequence_id,
                    message_type='notification',
                )
            
            # Preparar respuesta con información actualizada
            response_data = self._format_price_info(booking_line)
            response_data['change_info'] = {
                'old_price': float(old_price),
                'price_difference': float(new_price - old_price),
                'changed_by': request.env.user.name,
                'changed_at': datetime.now().isoformat(),
            }
            
            _logger.info(
                'Precio de línea %s cambiado por %s: %s -> %s. Motivo: %s',
                line_id,
                request.env.user.login,
                old_price,
                new_price,
                reason
            )
            
            return self._prepare_response(
                data=response_data,
                message=_('Precio actualizado exitosamente')
            )
            
        except (ValidationError, AccessError, UserError) as e:
            _logger.warning('Error de validación en change_price: %s', str(e))
            return self._prepare_response(error=str(e), status=400)
            
        except Exception as e:
            _logger.exception('Error inesperado en change_price: %s', str(e))
            return self._prepare_response(
                error=_('Error interno del servidor'),
                status=500
            )

    @http.route(
        '/api/hotel/booking_line/<int:line_id>/reset_price',
        auth='public',
        type='http',
        methods=['POST'],
        csrf=False
    )
    @validate_api_key
    def reset_price(self, line_id, **kw):
        """
        Restaurar precio original de una línea de reserva con validaciones completas
        
        Args:
            line_id: ID de la línea de reserva
            
        Returns:
            JSON con información del precio restaurado
        """
        try:
            # Validar acceso y obtener línea
            booking_line = self._check_booking_line_access(line_id)
            
            # Validaciones completas
            try:
                # Validar permisos de cambio de precio
                self._validate_price_change_permissions(booking_line)
                
                # Validar integridad de la línea
                self._validate_booking_line_integrity(booking_line)
                
                # Validar estado de la línea
                self._validate_booking_line_state(booking_line)
                
                # Validar permisos del usuario
                self._validate_user_permissions(booking_line)
                
            except (ValidationError, AccessError) as e:
                return self._prepare_response(error=str(e), status=400)
            
            # Verificar que existe precio original
            if not booking_line.original_price:
                return self._prepare_response(
                    error=_('No hay precio original registrado para restaurar'),
                    status=400
                )
            
            # Verificar que el precio actual es diferente al original
            if booking_line.price == booking_line.original_price:
                return self._prepare_response(
                    error=_('El precio ya está en su valor original'),
                    status=400
                )
            
            # Guardar precio actual para el log
            old_price = booking_line.price
            original_price = booking_line.original_price
            
            # Preparar valores de actualización
            update_vals = {
                'price': original_price,
                'discount': 0.0,
                'discount_reason': False,
            }
            
            # Actualizar en el contexto de un entorno transaccional
            with request.env.cr.savepoint():
                booking_line.write(update_vals)
                
                # Registrar cambio en el chatter
                message_body = _(
                    '<p><strong>Precio restaurado al original</strong></p>'
                    '<ul>'
                    '<li>Precio anterior: %s %s</li>'
                    '<li>Precio restaurado: %s %s</li>'
                    '<li>Usuario: %s</li>'
                    '</ul>'
                ) % (
                    booking_line.currency_id.symbol,
                    old_price,
                    booking_line.currency_id.symbol,
                    original_price,
                    request.env.user.name
                )
                
                booking_line.booking_id.message_post(
                    body=message_body,
                    subject=_('Precio restaurado - Línea %s') % booking_line.booking_sequence_id,
                    message_type='notification',
                )
            
            # Preparar respuesta con información actualizada
            response_data = self._format_price_info(booking_line)
            response_data['reset_info'] = {
                'old_price': float(old_price),
                'restored_price': float(original_price),
                'price_difference': float(original_price - old_price),
                'reset_by': request.env.user.name,
                'reset_at': datetime.now().isoformat(),
            }
            
            _logger.info(
                'Precio de línea %s restaurado por %s: %s -> %s',
                line_id,
                request.env.user.login,
                old_price,
                original_price
            )
            
            return self._prepare_response(
                data=response_data,
                message=_('Precio restaurado exitosamente')
            )
            
        except (ValidationError, AccessError, UserError) as e:
            _logger.warning('Error de validación en reset_price: %s', str(e))
            return self._prepare_response(error=str(e), status=400)
            
        except Exception as e:
            _logger.exception('Error inesperado en reset_price: %s', str(e))
            return self._prepare_response(
                error=_('Error interno del servidor'),
                status=500
            )

    # =============================================================================
    # ENDPOINTS BATCH (Operaciones múltiples)
    # =============================================================================

    @http.route(
        '/api/hotel/booking/<int:booking_id>/lines/price_info',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False
    )
    @validate_api_key
    def get_booking_lines_prices(self, booking_id, **kw):
        """
        Obtener información de precios de todas las líneas de una reserva
        
        Args:
            booking_id: ID de la reserva
            
        Returns:
            JSON con información de precios de todas las líneas
        """
        try:
            booking = request.env['hotel.booking'].browse(booking_id)
            
            if not booking.exists():
                raise ValidationError(_('Reserva con ID %s no encontrada') % booking_id)
            
            lines_info = []
            for line in booking.booking_line_ids:
                try:
                    lines_info.append(self._format_price_info(line))
                except Exception as e:
                    _logger.warning('Error procesando línea %s: %s', line.id, str(e))
                    continue
            
            summary = {
                'booking_id': booking_id,
                'booking_name': booking.sequence_id,
                'total_lines': len(booking.booking_line_ids),
                'total_original': sum(line.get('original_price', 0) for line in lines_info),
                'total_current': sum(line.get('current_price', 0) for line in lines_info),
                'total_discount': sum(line.get('discount_amount', 0) for line in lines_info),
                'lines': lines_info,
            }
            
            _logger.info('Información de precios obtenida para reserva %s', booking_id)
            
            return self._prepare_response(
                data=summary,
                message=_('Información obtenida exitosamente')
            )
            
        except (ValidationError, AccessError) as e:
            _logger.warning('Error en get_booking_lines_prices: %s', str(e))
            return self._prepare_response(error=str(e), status=403)
            
        except Exception as e:
            _logger.exception('Error inesperado en get_booking_lines_prices: %s', str(e))
            return self._prepare_response(
                error=_('Error interno del servidor'),
                status=500
            )