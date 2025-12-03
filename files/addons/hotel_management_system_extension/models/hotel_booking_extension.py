# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURACIÓN DE ESTADOS Y TRANSICIONES (Compatible con XML existente)
# =============================================================================

class BookingState:
    """Clase para definir constantes de estados - Compatible con XML"""
    # Estados principales
    INITIAL = 'initial'
    CONFIRMED = 'confirmed'
    CHECKIN = 'checkin'
    CHECKOUT = 'checkout'
    CLEANING_NEEDED = 'cleaning_needed'
    ROOM_READY = 'room_ready'
    CANCELLED = 'cancelled'
    NO_SHOW = 'no_show'
    
    # Estados legacy (compatibilidad con módulo base)
    DRAFT = 'draft'
    ALLOT = 'allot'
    CHECK_IN = 'check_in'
    PENDING = 'pending'
    CHECKOUT_PENDING = 'checkout_pending'

# Definición de estados con metadatos
BOOKING_STATES = {
    BookingState.INITIAL: {
        'name': 'Borrador',
        'description': 'Reserva en estado inicial',
        'color': 'secondary',
        'is_terminal': False,
        'requires_room': False
    },
    BookingState.CONFIRMED: {
        'name': 'Confirmada',
        'description': 'Reserva confirmada por el cliente',
        'color': 'info',
        'is_terminal': False,
        'requires_room': False
    },
    BookingState.CHECKIN: {
        'name': 'Check-in Realizado',
        'description': 'Huésped en la habitación',
        'color': 'success',
        'is_terminal': False,
        'requires_room': True
    },
    BookingState.CHECKOUT: {
        'name': 'Check-out Realizado',
        'description': 'Huésped ha salido',
        'color': 'primary',
        'is_terminal': False,
        'requires_room': True
    },
    BookingState.CLEANING_NEEDED: {
        'name': 'Limpieza Necesaria',
        'description': 'Habitación requiere limpieza',
        'color': 'warning',
        'is_terminal': False,
        'requires_room': True
    },
    BookingState.ROOM_READY: {
        'name': 'Habitación Lista',
        'description': 'Habitación lista para nuevo huésped',
        'color': 'success',
        'is_terminal': False,
        'requires_room': True
    },
    BookingState.CANCELLED: {
        'name': 'Cancelada',
        'description': 'Reserva cancelada',
        'color': 'danger',
        'is_terminal': True,
        'requires_room': False
    },
    BookingState.NO_SHOW: {
        'name': 'No Se Presentó',
        'description': 'Cliente no se presentó',
        'color': 'danger',
        'is_terminal': True,
        'requires_room': False
    },
    # Estados legacy
    BookingState.DRAFT: {
        'name': 'Borrador',
        'description': 'Estado borrador legacy',
        'color': 'secondary',
        'is_terminal': False,
        'requires_room': False
    },
    BookingState.ALLOT: {
        'name': 'Habitación Asignada',
        'description': 'Habitación asignada (legacy)',
        'color': 'warning',
        'is_terminal': False,
        'requires_room': True
    },
    BookingState.CHECK_IN: {
        'name': 'Check-in Legacy',
        'description': 'Check-in legacy',
        'color': 'success',
        'is_terminal': False,
        'requires_room': True
    }
}

# Reglas de transición optimizadas (compatible con XML)
STATE_TRANSITIONS = {
    BookingState.INITIAL: [BookingState.CONFIRMED, BookingState.CANCELLED],
    BookingState.CONFIRMED: [BookingState.CHECKIN, BookingState.CANCELLED, BookingState.NO_SHOW],
    BookingState.CHECKIN: [BookingState.CHECKOUT, BookingState.CANCELLED],
    BookingState.CHECKOUT: [BookingState.CLEANING_NEEDED],
    BookingState.CLEANING_NEEDED: [BookingState.ROOM_READY],
    BookingState.ROOM_READY: [BookingState.CONFIRMED],  # Para reutilizar habitación
    BookingState.CANCELLED: [BookingState.INITIAL],     # Permitir reactivar
    BookingState.NO_SHOW: [BookingState.INITIAL],       # Permitir reactivar
    
    # Estados legacy (compatibilidad)
    BookingState.DRAFT: [BookingState.CONFIRMED, BookingState.CANCELLED],
    BookingState.ALLOT: [BookingState.CHECKIN, BookingState.CANCELLED, BookingState.NO_SHOW],
    BookingState.CHECK_IN: [BookingState.CHECKOUT, BookingState.CANCELLED],
    BookingState.PENDING: [BookingState.CONFIRMED, BookingState.CANCELLED],
}


class StateTransitionValidator:
    """Clase para validar transiciones de estado"""
    
    @staticmethod
    def is_valid_transition(current_state, new_state):
        """Validar si una transición es permitida"""
        allowed_transitions = STATE_TRANSITIONS.get(current_state, [])
        return new_state in allowed_transitions
    
    @staticmethod
    def get_available_transitions(current_state):
        """Obtener transiciones disponibles"""
        return STATE_TRANSITIONS.get(current_state, [])
    
    @staticmethod
    def validate_transition_rules(booking, new_state):
        """Validar reglas específicas para transiciones"""
        errors = []
        
        # Validar habitación asignada
        state_info = BOOKING_STATES.get(new_state, {})
        if state_info.get('requires_room', False) and not booking.booking_line_ids:
            errors.append(_('Se requiere habitación asignada para el estado "%s"') % state_info.get('name', new_state))
        
        # Validar fechas para check-in
        if new_state == BookingState.CHECKIN:
            today = fields.Date.today()
            checkin_date = booking.check_in
            if checkin_date:
                # Manejo robusto de fechas para Odoo 17
                if isinstance(checkin_date, datetime):
                    checkin_date_obj = checkin_date.date()
                elif isinstance(checkin_date, str):
                    checkin_date_obj = fields.Date.from_string(checkin_date)
                else:
                    checkin_date_obj = checkin_date
                
                if checkin_date_obj and checkin_date_obj > today:
                    errors.append(_('No se puede realizar check-in antes de la fecha programada'))
        
        # Validar fechas para check-out
        if new_state == BookingState.CHECKOUT:
            if not booking.check_out:
                errors.append(_('Debe especificar la fecha de check-out'))
        
        return errors


class HotelBookingExtension(models.Model):
    _inherit = 'hotel.booking'
    
    # Heredar campos del módulo padre para compatibilidad con Create Invoice
    is_show_create_invoice_btn = fields.Boolean(
        "Is show Create Button", 
        compute="_compute_show_btn",
        help="Campo heredado del módulo padre para controlar visibilidad del botón Create Invoice"
    )
    
    def _compute_show_btn(self):
        """
        Método heredado del módulo padre para controlar la visibilidad del botón Create Invoice.
        Mantiene la misma lógica: si auto_invoice_gen está activado, oculta el botón manual.
        """
        is_show_create_invoice_btn = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("hotel_management_system.auto_invoice_gen")
        )
        for rec in self:
            rec.is_show_create_invoice_btn = is_show_create_invoice_btn
    
    # =============================================================================
    # CAMPOS DEL MODELO - Compatible con XML existente
    # =============================================================================
    
    # Campo para motivo de viaje
    motivo_viaje = fields.Char(
        string='Motivo de Viaje',
        help='Especifique el motivo o propósito del viaje del huésped',
        tracking=True
    )
    
    # --- NUEVOS CAMPOS PARA INGRESO MANUAL ---
    
    early_checkin_charge = fields.Monetary(
        string="Cargo por Early Check-in",
        currency_field='currency_id',
        help="Ingrese el monto a cobrar por el ingreso anticipado. Poner en 0 para anular."
    )
    late_checkout_charge = fields.Monetary(
        string="Cargo por Late Check-out",
        currency_field='currency_id',
        help="Ingrese el monto a cobrar por la salida tardía. Poner en 0 para anular."
    )
    
    # Campo computado para la suma de cargos adicionales
    additional_charges_total = fields.Monetary(
        string="Total Cargos Adicionales",
        currency_field='currency_id',
        compute='_compute_additional_charges_total',
        store=True,
        help="Suma total de cargos por Early Check-in y Late Check-out"
    )
    
    # --- CAMPOS DE CONFIGURACIÓN ---
    early_checkin_product_id = fields.Many2one(
        'product.product', 
        string="Producto para Early Check-in",
        help="Producto de tipo servicio que se usará para registrar el cargo de Early Check-in.",
        default=lambda self: self.env.ref('hotel_management_system_extension.product_service_early_checkin', raise_if_not_found=False)
    )
    late_checkout_product_id = fields.Many2one(
        'product.product', 
        string="Producto para Late Check-out",
        help="Producto de tipo servicio que se usará para registrar el cargo de Late Check-out.",
        default=lambda self: self.env.ref('hotel_management_system_extension.product_service_late_checkout', raise_if_not_found=False)
    )

    
    # =============================================================================
    # CAMPOS DE DESCUENTO Y PRECIO ORIGINAL
    # =============================================================================
    
    # Precio original de la habitación, para no perderlo
    original_price = fields.Monetary(
        string="Precio Original", 
        compute='_compute_original_price',
        store=True,
        readonly=True, 
        tracking=True,
        help="Precio original de la habitación antes de cualquier descuento"
    )
    
    # Monto del descuento aplicado
    discount_amount = fields.Monetary(
        string="Monto Descontado", 
        compute='_compute_discount_amount',
        store=True,
        readonly=True, 
        tracking=True,
        help="Monto total del descuento aplicado a la reserva (calculado automáticamente)"
    )
    
    # Razón del descuento
    discount_reason = fields.Text(
        string="Razón del Descuento/Cambio", 
        tracking=True,
        help="Explicación del motivo del descuento o cambio de precio"
    )
    
    # Extender el campo status_bar con los estados del XML
    status_bar = fields.Selection(
        selection_add=[
            ('confirmed', 'CONFIRMADA'),
            ('checkin', 'CHECK-IN'),
            ('checkout', 'CHECK-OUT'),
            ('cleaning_needed', 'LIMPIEZA NECESARIA'),
            ('room_ready', 'HABITACION LISTA'),
            ('no_show', 'NO SE PRESENTO'),
            ('cancelled', 'CANCELADA'),
        ],
        ondelete={
            'confirmed': 'set default',
            'checkin': 'set default', 
            'checkout': 'set default',
            'cleaning_needed': 'set default',
            'room_ready': 'set default',
            'no_show': 'set default',
            'cancelled': 'set default',
        }
    )
    
    # Campos computados para la lógica de botones (requeridos por XML)
    is_check_in_allowed = fields.Boolean(
        string='Check-in Permitido',
        compute='_compute_available_actions',
        help='Indica si se puede realizar check-in'
    )
    
    is_checkout_allowed = fields.Boolean(
        string='Check-out Permitido',
        compute='_compute_available_actions',
        help='Indica si se puede realizar check-out'
    )
    
    is_cancellation_allowed = fields.Boolean(
        string='Cancelación Permitida',
        compute='_compute_available_actions',
        help='Indica si se puede cancelar la reserva'
    )
    
    is_room_change_allowed = fields.Boolean(
        string='Cambio de Habitación Permitido',
        compute='_compute_available_actions',
        help='Indica si se puede cambiar de habitación (solo en estado check-in)'
    )
    
    is_cleaning_request_allowed = fields.Boolean(
        string='Solicitud de Limpieza Permitida',
        compute='_compute_available_actions',
        help='Indica si se puede solicitar limpieza (solo en estado checkout)'
    )
    
    is_sync_services_allowed = fields.Boolean(
        string='Sincronización de Servicios Permitida',
        compute='_compute_available_actions',
        help='Indica si se puede sincronizar servicios (solo en reservas con cambio de habitación)'
    )
    
    # Campos para conexión de reservas (cambio de habitación)
    connected_booking_id = fields.Many2one(
        'hotel.booking',
        string='Reserva Conectada',
        help='Reserva conectada por cambio de habitación'
    )
    
    split_from_booking_id = fields.Many2one(
        'hotel.booking',
        string='Continuación de Reserva',
        readonly=True,
        help='Reserva original de la que se originó este cambio de habitación'
    )
    
    # Campos para servicios adicionales manuales
    manual_service_description = fields.Char(
        string='Descripción del Servicio',
        help='Descripción del servicio adicional'
    )
    
    manual_service_amount = fields.Monetary(
        string='Costo del Servicio',
        currency_field='currency_id',
        help='Costo del servicio adicional que se sumará a la factura'
    )
    
    # Campo computed para mostrar solo servicios manuales
    manual_service_lines = fields.One2many(
        'hotel.booking.service.line',
        'booking_id',
        string='Servicios Manuales',
        compute='_compute_manual_service_lines',
        help='Servicios adicionales agregados manualmente'
    )
    
    @api.depends('hotel_service_lines')
    def _compute_manual_service_lines(self):
        """Filtrar solo los servicios manuales"""
        for record in self:
            # Buscar servicios que tengan el servicio genérico "Servicio Manual"
            manual_services = record.hotel_service_lines.filtered(
                lambda s: s.service_id and s.service_id.name == 'Servicio Manual'
            )
            record.manual_service_lines = manual_services

    @api.onchange('manual_service_amount')
    def _onchange_manual_service_amount(self):
        """Hacer la descripción obligatoria solo si se ingresa un precio"""
        if self.manual_service_amount and self.manual_service_amount > 0:
            if not self.manual_service_description:
                return {
                    'warning': {
                        'title': _('Descripción Requerida'),
                        'message': _('Debe ingresar una descripción del servicio cuando se especifica un precio.'),
                    }
                }
        return {}
    
    is_room_change_origin = fields.Boolean(
        string='Es Origen de Cambio',
        default=False,
        help='Indica si esta reserva es el origen de un cambio de habitación'
    )
    
    is_room_change_destination = fields.Boolean(
        string='Es Destino de Cambio', 
        default=False,
        help='Indica si esta reserva es el destino de un cambio de habitación'
    )
    
    # Campos adicionales para información de estado
    state_color = fields.Char(
        string='Color del Estado',
        compute='_compute_state_info'
    )
    
    state_description = fields.Char(
        string='Descripción del Estado',
        compute='_compute_state_info'
    )
    
    available_actions = fields.Char(
        string='Acciones Disponibles',
        compute='_compute_available_actions'
    )
    

    
    # =============================================================================
    # MÉTODOS COMPUTADOS
    # =============================================================================
    
    @api.depends('booking_line_ids', 'booking_line_ids.product_id', 'booking_line_ids.product_id.product_tmpl_id.list_price')
    def _compute_original_price(self):
        """
        Computar el precio original basándose en los precios de lista de los productos
        Este método se ejecuta automáticamente cuando cambian las líneas de reserva
        """
        for record in self:
            total_original = 0.0
            
            if record.booking_line_ids:
                for line in record.booking_line_ids:
                    if line.product_id and line.product_id.product_tmpl_id:
                        # Usar el precio de lista del template del producto
                        list_price = line.product_id.product_tmpl_id.list_price or 0.0
                        total_original += list_price
            
            record.original_price = total_original
            
            # Log para debugging
            if total_original == 0 and record.booking_line_ids:
                _logger.warning(
                    'Booking %s: Original price is 0 but has %s booking lines. '
                    'Check product list prices.',
                    record.id, len(record.booking_line_ids)
                )
    
    @api.depends('status_bar')
    def _compute_state_info(self):
        """Computar información del estado actual"""
        for record in self:
            current_state = record.status_bar or BookingState.INITIAL
            state_info = BOOKING_STATES.get(current_state, {})
            
            record.state_color = state_info.get('color', 'secondary')
            record.state_description = state_info.get('description', 'Estado desconocido')
    
    @api.depends('status_bar')
    def _compute_available_actions(self):
        """Computar acciones disponibles basadas en el estado"""
        for record in self:
            current_state = record.status_bar or BookingState.INITIAL
            available_transitions = StateTransitionValidator.get_available_transitions(current_state)
            
            # Acciones específicas requeridas por XML
            record.is_check_in_allowed = current_state == BookingState.CONFIRMED
            record.is_checkout_allowed = current_state == BookingState.CHECKIN
            record.is_cancellation_allowed = current_state in [BookingState.INITIAL, BookingState.CONFIRMED]
            
            # NUEVA LÓGICA: Cambio de habitación solo permitido en estado check-in
            record.is_room_change_allowed = current_state == BookingState.CHECKIN
            
            # NUEVA LÓGICA: Solicitud de limpieza solo permitida en estado checkout
            record.is_cleaning_request_allowed = current_state == BookingState.CHECKOUT
            
            # NUEVA LÓGICA: Sincronización de servicios permitida en reservas con cambio de habitación o en estado checkout
            record.is_sync_services_allowed = (
                current_state == BookingState.CHECKOUT
                or record.is_room_change_origin
                or record.is_room_change_destination
                or bool(record.connected_booking_id)
            )
            
            # Convertir transiciones disponibles a string para el campo compute
            record.available_actions = ','.join(available_transitions)
    
    # =============================================================================
    # MÉTODOS ONCHANGE PARA DESCUENTOS Y PRECIOS
    # =============================================================================
    
    @api.onchange('booking_line_ids')
    def _onchange_booking_line_ids_for_price(self):
        """
        Vigilar cambios en las líneas de reserva para actualizar razón del descuento
        El descuento se calcula automáticamente por el campo computado
        """
        if self.booking_line_ids:
            # Solo actualizar la razón del descuento si hay descuento y no hay razón
            if self.discount_amount > 0 and not self.discount_reason:
                self.discount_reason = "Descuento aplicado"
            elif self.discount_amount == 0.0:
                self.discount_reason = ""
    
    @api.onchange('discount_reason')
    def _onchange_discount_reason(self):
        """
        Validar que si hay descuento, debe haber una razón
        """
        if self.discount_amount > 0 and not self.discount_reason:
            return {
                'warning': {
                    'title': _('Razón de Descuento Requerida'),
                    'message': _('Por favor especifique la razón del descuento aplicado.')
                }
            }
    
    # --- MÉTODOS ONCHANGE PARA LA AUTOMATIZACIÓN ---

    @api.depends('early_checkin_charge', 'late_checkout_charge', 'hotel_service_lines.amount')
    def _compute_additional_charges_total(self):
        """
        Calcular la suma total de cargos adicionales
        """
        for record in self:
            # Servicios especiales (early checkin, late checkout)
            special_charges = (record.early_checkin_charge or 0) + (record.late_checkout_charge or 0)
            
            # Servicios manuales agregados
            manual_services_total = sum(
                service.amount for service in record.hotel_service_lines 
                if service.service_id and service.service_id.name == 'Servicio Manual'
            )
            
            record.additional_charges_total = special_charges + manual_services_total

    @api.depends("booking_line_ids.subtotal_price", "early_checkin_charge", "late_checkout_charge", "hotel_service_lines.amount")
    def _compute_actual_amount(self):
        """
        Sobrescribir el método del módulo base para incluir cargos adicionales
        """
        for booking in self:
            total_tax_amount = 0
            total_amount = 0
            
            # Calcular totales de las líneas de reserva (lógica original)
            for line in booking.booking_line_ids:
                total_tax_amount += line.taxed_price
                total_amount += line.subtotal_price
            
            # Agregar cargos adicionales al total
            additional_charges = (booking.early_checkin_charge or 0) + (booking.late_checkout_charge or 0)
            
            # Agregar servicios manuales al total
            manual_services_total = sum(
                service.amount for service in booking.hotel_service_lines 
                if service.service_id and service.service_id.name == 'Servicio Manual'
            )
            
            # Actualizar campos
            booking.tax_amount = total_tax_amount - total_amount
            booking.amount_untaxed = total_amount + additional_charges + manual_services_total
            booking.total_amount = total_tax_amount + additional_charges + manual_services_total
            
            # Debug log para verificar cálculos
            _logger.info(f"Booking ID {booking.id}: Base amount={total_amount}, Additional charges={additional_charges}, Manual services={manual_services_total}, Final total={booking.total_amount}")

    @api.onchange('early_checkin_charge')
    def _onchange_early_checkin_charge(self):
        """
        Manejar cambios en el cargo de Early Check-in
        """
        # Forzar el recálculo del total amount
        if self.early_checkin_charge or self.late_checkout_charge:
            self._compute_actual_amount()
            
        # Mostrar mensaje informativo si se agrega un cargo
        if self.early_checkin_charge and self.early_checkin_charge > 0:
            return {
                'warning': {
                    'title': _('Cargo por Early Check-in Agregado'),
                    'message': _('Se ha agregado un cargo de %s por Early Check-in. El total de la reserva se ha actualizado automáticamente.') % self.early_checkin_charge
                }
            }

    @api.onchange('late_checkout_charge')
    def _onchange_late_checkout_charge(self):
        """
        Manejar cambios en el cargo de Late Check-out
        """
        # Forzar el recálculo del total amount
        if self.early_checkin_charge or self.late_checkout_charge:
            self._compute_actual_amount()
            
        # Mostrar mensaje informativo si se agrega un cargo
        if self.late_checkout_charge and self.late_checkout_charge > 0:
            return {
                'warning': {
                    'title': _('Cargo por Late Check-out Agregado'),
                    'message': _('Se ha agregado un cargo de %s por Late Check-out. El total de la reserva se ha actualizado automáticamente.') % self.late_checkout_charge
                }
            }

    
    def action_add_extra_service(self):
        """
        Este método abre una ventana emergente (wizard/pop-up) para
        crear una nueva línea de servicio o costo extra.
        """
        self.ensure_one()
        
        # Verificar que hay líneas de reserva (booking_line_ids)
        if not self.booking_line_ids:
            raise UserError(_('Debe agregar habitaciones a la reserva antes de añadir servicios.'))
        
        # Usar la primera línea de reserva como booking_line_id por defecto
        default_booking_line_id = self.booking_line_ids[0].id
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Añadir Costo Extra',
            'res_model': 'hotel.booking.service.line',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_booking_line_id': default_booking_line_id,
                'default_booking_id': self.id,
            },
            'view_id': self.env.ref('hotel_management_system_extension.view_hotel_booking_service_line_form').id,
        }
    
    def _set_original_price_from_room(self, room_line):
        """
        Establecer el precio original basado en una línea de habitación específica
        """
        if room_line and room_line.product_id:
            # Obtener el precio de la habitación
            room_price = room_line.price or room_line.product_id.list_price
            if room_price > 0:
                self.original_price = room_price
                # Si no hay descuento, el precio total es igual al original
                if not self.discount_amount:
                    self.discount_amount = 0.0
    
    def _compute_original_price_from_booking_lines(self):
        """
        Método legacy mantenido para compatibilidad
        Ahora solo fuerza el recálculo del campo computado
        """
        # Forzar recálculo del campo computado
        self._compute_original_price()
        return self.original_price
    
    @api.depends('booking_line_ids', 'booking_line_ids.discount_amount', 'booking_line_ids.original_price', 'booking_line_ids.price')
    def _compute_discount_amount(self):
        """
        Computar el monto total descontado basándose en las líneas de reserva
        Este método se ejecuta automáticamente cuando cambian los precios o descuentos
        """
        for record in self:
            total_discount = 0.0
            
            if record.booking_line_ids:
                for line in record.booking_line_ids:
                    # Calcular descuento por línea
                    line_discount = 0.0
                    if line.original_price and line.price:
                        if line.original_price > line.price:
                            line_discount = line.original_price - line.price
                    
                    total_discount += line_discount
            
            record.discount_amount = total_discount
            
            # Log para debugging
            _logger.info(
                'Booking %s: Discount amount computed: %s (from %s lines)',
                record.id, total_discount, len(record.booking_line_ids)
            )
    
    def force_compute_discount_amount(self):
        """
        Método para forzar el recálculo del descuento
        Útil para corregir reservas existentes con descuentos incorrectos
        """
        self.ensure_one()
        
        # Forzar recálculo
        self._compute_discount_amount()
        
        # Log del resultado
        _logger.info(
            'Booking %s: Forced discount computation. Result: %s (from %s lines)',
            self.id, self.discount_amount, len(self.booking_line_ids)
        )
        
        return self.discount_amount
    
    def _recompute_booking_amounts(self):
        """
        Recalcular los montos de la reserva principal basándose en las líneas
        Solo se ejecuta cuando es necesario
        """
        self.ensure_one()
        
        # Solo recalcular si hay líneas y no viene del modal
        if (self.booking_line_ids and 
            not self.env.context.get('is_add_rooms_modal')):
            
            total_subtotal = 0
            total_taxed = 0
            
            for line in self.booking_line_ids:
                total_subtotal += line.subtotal_price or 0
                total_taxed += line.taxed_price or 0
            
            # El precio original se calcula automáticamente por el campo computado
            # No es necesario calcularlo manualmente aquí
            
            # Solo actualizar si hay cambios significativos
            if total_subtotal > 0 or total_taxed > 0:
                self.write({
                    'amount_untaxed': total_subtotal,
                    'total_amount': total_taxed,
                    'tax_amount': total_taxed - total_subtotal
                })
    
    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False, submenu=False):
        """
        Sobrescribir para forzar el recálculo cuando se abre la vista
        """
        result = super().fields_view_get(view_id, view_type, toolbar, submenu)
        
        # Si es vista de formulario, forzar el recálculo de descuentos
        if view_type == 'form' and self.env.context.get('active_id'):
            booking = self.browse(self.env.context['active_id'])
            if booking.exists():
                # El precio original y descuento se calculan automáticamente por campos computados
                # Solo actualizar la razón del descuento si es necesario
                if booking.discount_amount > 0 and not booking.discount_reason:
                    booking.discount_reason = "Descuento aplicado"
        
        return result
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribir create para logging de fechas y debugging del desfase +1 día
        Mejorado para Odoo 17
        """
        # Log de debugging para fechas
        for vals in vals_list:
            if 'check_in' in vals or 'check_out' in vals:
                _logger.info(
                    'DEBUG - Creando reserva con fechas: check_in=%s, check_out=%s, '
                    'check_in_type=%s, check_out_type=%s',
                    vals.get('check_in'),
                    vals.get('check_out'),
                    type(vals.get('check_in')).__name__,
                    type(vals.get('check_out')).__name__
                )
        
        # Crear la reserva
        result = super().create(vals_list)
        
        # Log adicional después de la creación
        for record in result:
            _logger.info(
                'DEBUG - Reserva creada ID=%s: check_in=%s, check_out=%s, '
                'check_in_date=%s, check_out_date=%s',
                record.id,
                record.check_in,
                record.check_out,
                record.check_in.date() if record.check_in else None,
                record.check_out.date() if record.check_out else None
            )
        
        return result
    
    # =============================================================================
    # MÉTODOS DE TRANSICIÓN DE ESTADO
    # =============================================================================
    
    def action_confirm_booking(self):
        """
        Sobrescribir el método de confirmación para usar nuestra lógica de creación de órdenes de venta
        """
        _logger.info('=== CONFIRMANDO RESERVA %s ===', self.id)
        
        # Ejecutar validaciones del módulo padre
        self.validate_guest()
        if not self.env.context.get("bypass_checkin_checkout", False):
            self._check_validity_check_in_check_out_booking()

        if self.status_bar == "initial":
            # Validaciones de comisión de agente (del módulo padre)
            if self.booking_reference == 'via_agent' and self.commission_type == 'fixed' and not self.agent_commission_amount:
                raise ValidationError(_("Please specify the agent commission on agent info tab!"))
            if self.booking_reference == 'via_agent' and self.commission_type == 'percentage' and not self.agent_commission_percentage:
                raise ValidationError(_("Please specify the agent commission on agent info tab!"))
            
            # Validaciones básicas
            if not self.booking_line_ids:
                raise ValidationError(_("Please add rooms for booking confirmation!"))
            if not all([line.guest_info_ids.ids for line in self.booking_line_ids]):
                raise ValidationError(_("Please fill the members details !!"))
            
            # Crear orden de venta solo si no es desde sale_order
            if self.booking_reference != "sale_order":
                _logger.info('Creando orden de venta para reserva %s', self.id)
                
                try:
                    # Usar nuestra lógica mejorada de creación de órdenes de venta
                    sale_order = self._create_sale_order_for_booking()
                    if sale_order:
                        self.order_id = sale_order
                        _logger.info('Orden de venta %s asignada a reserva %s', sale_order.id, self.id)
                    else:
                        _logger.error('_create_sale_order_for_booking() retornó False para reserva %s', self.id)
                        raise ValidationError(_("No se pudo crear la orden de venta para la reserva. Verifique que la reserva tenga habitaciones asignadas y todos los datos requeridos."))
                except Exception as e:
                    _logger.error('Error en action_confirm_booking para reserva %s: %s', self.id, str(e))
                    raise ValidationError(_("Error al crear la orden de venta: %s") % str(e))
            
            # Cambiar estado a confirmado
            self.status_bar = "confirmed"  # Usar nuestro estado
            _logger.info('Reserva %s confirmada exitosamente', self.id)
            
            # Ejecutar lógica adicional del módulo padre si existe
            if hasattr(super(), 'manage_check_in_out_based_on_restime'):
                self.manage_check_in_out_based_on_restime()
            
            # Enviar email de confirmación si existe
            try:
                template_id = self.env.ref("hotel_management_system.hotel_booking_confirm_id")
                if template_id:
                    template_id.send_mail(self.id, force_send=True)
            except Exception as e:
                _logger.warning('No se pudo enviar email de confirmación: %s', str(e))
        
        return True
    
    def _change_state(self, new_state, additional_validations=None):
        """
        Método centralizado para cambio de estado con validaciones
        
        :param new_state: Nuevo estado a asignar
        :param additional_validations: Función adicional de validación
        :return: True si el cambio fue exitoso
        """
        self.ensure_one()
        
        current_state = self.status_bar or BookingState.INITIAL
        
        # Validar transición
        if not StateTransitionValidator.is_valid_transition(current_state, new_state):
            available = StateTransitionValidator.get_available_transitions(current_state)
            raise UserError(_(
                'Transición no permitida. Desde "%s" solo se puede ir a: %s'
            ) % (BOOKING_STATES.get(current_state, {}).get('name', current_state),
                 ', '.join([BOOKING_STATES.get(s, {}).get('name', s) for s in available])))
        
        # Validaciones específicas del estado
        validation_errors = StateTransitionValidator.validate_transition_rules(self, new_state)
        if validation_errors:
            raise ValidationError('\n'.join(validation_errors))
        
        # Validaciones adicionales si se proporcionan
        if additional_validations:
            additional_validations(self, new_state)
        
        # Actualizar estado
        self.write({'status_bar': new_state})
        
        # Log de transición
        self._log_state_transition(current_state, new_state)
        
        return True
    
    def _log_state_transition(self, old_state, new_state):
        """Registrar cambio de estado en el chatter"""
        old_name = BOOKING_STATES.get(old_state, {}).get('name', old_state)
        new_name = BOOKING_STATES.get(new_state, {}).get('name', new_state)
        
        self.message_post(
            body=_('Estado cambiado de <b>%s</b> a <b>%s</b>') % (old_name, new_name),
            subject=_('Cambio de Estado de Reserva'),
            message_type='notification'
        )
        
        _logger.info(
            'Booking %s: State changed from %s to %s by user %s',
            self.id, old_state, new_state, self.env.user.name
        )
    
    # =============================================================================
    # ACCIONES DE ESTADO ESPECÍFICAS (Compatible con XML)
    # =============================================================================
    
    def action_check_in_with_documents(self):
        """
        Redirigir directamente a check-in sin abrir el wizard de documentos.
        """
        return self.action_check_in()

    def action_check_in(self):
        """
        Cambiar el estado de la reserva a checkin
        Solo disponible cuando el estado es 'confirmed'
        """
        self.ensure_one()
        
        if self.status_bar != 'confirmed':
            raise UserError(_('Solo se puede realizar check-in cuando la reserva está confirmada.'))
        
        # Validar que la fecha de check-in sea hoy o en el pasado
        today = fields.Date.today()
        
        # Manejo robusto de fechas para Odoo 17
        check_in_date = self.check_in
        if isinstance(check_in_date, datetime):
            check_in_date = check_in_date.date()
        elif isinstance(check_in_date, str):
            check_in_date = fields.Date.from_string(check_in_date)
        
        if check_in_date and check_in_date > today:
            raise UserError(_('No se puede realizar check-in antes de la fecha programada.'))
        
        # Validar que haya habitaciones asignadas
        if not self.booking_line_ids:
            raise UserError(_('Debe asignar habitaciones antes del check-in.'))
        
        self.write({'status_bar': 'checkin'})
        
        # Actualizar estado de habitaciones si existe el campo
        for line in self.booking_line_ids:
            if hasattr(line.product_id, 'room_status'):
                line.product_id.room_status = 'occupied'
        
        # Crear mensaje de seguimiento
        self.message_post(
            body=_('Check-in realizado exitosamente. El huésped está ahora en la habitación.'),
            subject=_('Check-in Completado')
        )
        
        return True
    
    def action_checkout(self):
        """
        Realizar check-out siguiendo las reglas del módulo base pero con mejoras
        """
        self.ensure_one()
        
        if self.status_bar != 'checkin':
            raise UserError(_('Solo se puede realizar check-out cuando el huésped está en la habitación.'))
        
        # Procesar servicios del módulo base
        self._process_checkout_services()
        
        # Cambiar el estado a checkout
        self.write({'status_bar': 'checkout'})
        
        # Automáticamente pasar a limpieza si está configurado
        if self.env.context.get('auto_cleaning', True):
            self.write({'status_bar': 'cleaning_needed'})
        
        # Crear mensaje de seguimiento
        self.message_post(
            body=_('Check-out completado. El huésped ha salido de la habitación.'),
            subject=_('Check-out Completado')
        )
        
        return True
    
    def action_no_show(self):
        """
        Cambiar el estado a no_show
        Solo disponible en estado 'confirmed'
        """
        self.ensure_one()
        
        if self.status_bar != 'confirmed':
            raise UserError(_('Solo se puede marcar como No Show en reservas confirmadas.'))
        
        # Validar que haya pasado la fecha de check-in
        today = fields.Date.today()
        
        # Manejo robusto de fechas
        checkin_date = self.check_in
        if isinstance(checkin_date, datetime):
            checkin_date = checkin_date.date()
        elif isinstance(checkin_date, str):
            checkin_date = fields.Date.from_string(checkin_date)
        
        if checkin_date and checkin_date >= today:
            raise UserError(_('Solo se puede marcar como No Show después de la fecha de entrada.'))
        
        self.write({'status_bar': 'no_show'})
        
        # Liberar habitaciones
        self._release_rooms()
        
        # Aplicar políticas de no show
        self._apply_no_show_policy()
        
        # Crear mensaje de seguimiento
        self.message_post(
            body=_('Reserva marcada como No Show. El huésped no se presentó.'),
            subject=_('No Show Registrado')
        )
        
        return True
    
    def action_set_to_draft(self):
        """
        Regresar el estado a initial (borrador)
        Solo disponible en estados 'cancelled', 'no_show'
        """
        self.ensure_one()
        
        if self.status_bar not in ['cancelled', 'no_show']:
            raise UserError(_('Solo se puede regresar a borrador desde estados cancelados o no show.'))
        
        self.write({'status_bar': 'initial'})
        
        # Crear mensaje de seguimiento
        self.message_post(
            body=_('Reserva regresada a estado borrador.'),
            subject=_('Reserva en Borrador')
        )
        
        return True   
    
    def action_mark_cleaning_needed(self):
        """Marcar habitación para limpieza"""
        return self._change_state(BookingState.CLEANING_NEEDED)
    
    def action_request_cleaning(self):
        """Acción específica para solicitar limpieza después del checkout"""
        for booking in self:
            if booking.status_bar == 'checkout':
                booking.status_bar = 'cleaning_needed'
                # Agregar mensaje en el chatter
                booking.message_post(
                    body=f"Limpieza solicitada después del checkout por {self.env.user.name}",
                    message_type='notification'
                )
        return True
    
    def action_request_cleaning_from_booking(self):
        """Acción para solicitar limpieza desde el header de la reserva"""
        return self.action_request_cleaning()
    
    def action_add_manual_service(self):
        """Agregar servicio adicional manual a la reserva"""
        self.ensure_one()
        
        # Validar que si hay precio, debe haber descripción
        if self.manual_service_amount and self.manual_service_amount > 0:
            if not self.manual_service_description:
                raise UserError(_('Debe ingresar una descripción del servicio cuando se especifica un precio.'))
        
        # Validar que al menos uno de los campos esté lleno
        if not self.manual_service_description and not self.manual_service_amount:
            raise UserError(_('Debe ingresar al menos una descripción o un precio para el servicio adicional.'))
        
        if not self.booking_line_ids:
            raise UserError(_('Debe tener al menos una línea de reserva para agregar servicios.'))
        
        # Usar la primera línea de reserva como referencia
        booking_line = self.booking_line_ids[0]
        
        # Buscar o crear un servicio genérico para servicios manuales
        generic_service = self.env['hotel.service'].search([
            ('name', '=', 'Servicio Manual'),
            ('service_type', '=', 'paid')
        ], limit=1)
        
        if not generic_service:
            # Crear un servicio genérico si no existe
            generic_service = self.env['hotel.service'].create({
                'name': 'Servicio Manual',
                'service_type': 'paid',
                'amount': 0.0,  # El monto se define en cada línea
                'amount_type': 'fixed',
            })
        
        # Crear el servicio adicional
        service_vals = {
            'booking_id': self.id,
            'booking_line_id': booking_line.id,
            'service_id': generic_service.id,
            'amount': self.manual_service_amount or 0.0,  # Usar 0.0 si no hay precio
            'note': self.manual_service_description or 'Servicio sin descripción',  # Usar descripción por defecto si no hay
            'state': 'confirm',  # Confirmado automáticamente
        }
        
        # Crear la línea de servicio
        service_line = self.env['hotel.booking.service.line'].create(service_vals)
        
        # Debug: Verificar que el servicio se creó
        _logger.info(f"Servicio creado: ID={service_line.id}, Service ID={service_line.service_id.id}, Name={service_line.service_id.name}")
        
        # Guardar los valores para el mensaje antes de limpiar
        description = self.manual_service_description
        amount = self.manual_service_amount
        
        # Limpiar los campos después de agregar el servicio
        self.write({
            'manual_service_description': False,
            'manual_service_amount': 0.0
        })
        
        # Forzar la actualización del campo computed
        self._compute_manual_service_lines()
        
        # Forzar el recálculo de totales para incluir el nuevo servicio
        self._compute_additional_charges_total()
        self._compute_actual_amount()
        
        # Debug: Verificar cuántos servicios manuales hay
        _logger.info(f"Servicios manuales encontrados: {len(self.manual_service_lines)}")
        _logger.info(f"Total cargos adicionales: {self.additional_charges_total}")
        _logger.info(f"Total amount: {self.total_amount}")
        
        # Mensaje de confirmación
        self.message_post(
            body=f"Servicio adicional agregado: {description} - {self.currency_id.symbol}{amount}",
            message_type='notification'
        )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def action_mark_room_ready(self):
        """Marcar habitación como lista - NO modificar reserva existente"""
        result = self._change_state(BookingState.ROOM_READY)
        
        # NO modificar la reserva existente - solo cambiar el estado
        # La reserva original se mantiene intacta para historial
        
        # Actualizar estado de habitaciones para que estén disponibles
        for line in self.booking_line_ids:
            if hasattr(line.product_id, 'room_status'):
                line.product_id.room_status = 'available'
        
        # Crear mensaje de seguimiento
        self.message_post(
            body=_('Habitación marcada como lista. La reserva original se mantiene intacta. Disponible para crear NUEVA reserva.'),
            subject=_('Habitación Lista')
        )
        
        return result
    
    def action_reuse_room_ready_booking(self):
        """
        Crear una nueva reserva basada en una reserva en estado 'room_ready'
        """
        self.ensure_one()
        
        if self.status_bar != 'room_ready':
            raise UserError(_('Solo se pueden crear nuevas reservas desde reservas en estado "Habitación Lista".'))
        
        # Crear una nueva reserva basada en la actual
        new_booking_vals = {
            'partner_id': False,  # Se llenará con el nuevo cliente
            'check_in': False,    # Se llenará con las nuevas fechas
            'check_out': False,   # Se llenará con las nuevas fechas
            'hotel_id': self.hotel_id.id if self.hotel_id else False,
            'user_id': self.env.user.id,
            'status_bar': 'confirmed',  # Nueva reserva confirmada
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'pricelist_id': self.pricelist_id.id if self.pricelist_id else False,
        }
        
        # Crear la nueva reserva
        new_booking = self.env['hotel.booking'].create(new_booking_vals)
        
        # Copiar las líneas de habitación de la reserva original
        for line in self.booking_line_ids:
            new_line_vals = {
                'booking_id': new_booking.id,
                'product_id': line.product_id.id,
                'booking_days': 0,  # Se calculará con las nuevas fechas
                'price': line.price,
                'discount': line.discount,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
            }
            self.env['hotel.booking.line'].create(new_line_vals)
        
        # Crear mensaje de seguimiento en la reserva original
        self.message_post(
            body=_('Nueva reserva creada: <a href="#" data-oe-model="hotel.booking" data-oe-id="%s">%s</a>') % (new_booking.id, new_booking.sequence_id),
            subject=_('Nueva Reserva Creada')
        )
        
        # Crear mensaje de seguimiento en la nueva reserva
        new_booking.message_post(
            body=_('Reserva creada desde reserva anterior: <a href="#" data-oe-model="hotel.booking" data-oe-id="%s">%s</a>') % (self.id, self.sequence_id),
            subject=_('Reserva Creada desde Anterior')
        )
        
        return new_booking

    def action_register_payment(self):
        """
        Sobrescribir el método de pago por adelantado para manejar reservas sin orden de venta
        """
        self.ensure_one()
        
        # Si no hay orden de venta, crear una automáticamente
        if not self.order_id:
            # Crear una orden de venta básica para la reserva
            sale_order = self._create_sale_order_for_booking()
            if not sale_order:
                raise UserError(_("No se pudo crear la orden de venta para el pago por adelantado."))
        
        # Llamar al método original del módulo base
        return super().action_register_payment()

    def action_view_compute_bill(self):
        """
        Sobrescribir para funcionar exactamente como el módulo padre
        NO crear órdenes de venta automáticamente
        """
        self.ensure_one()
        
        # Validar que el estado sea correcto para Print Bill
        # Estados válidos: checkin, checkout, cleaning_needed, room_ready, allot
        valid_states = ['checkin', 'checkout', 'cleaning_needed', 'room_ready', 'allot']
        if self.status_bar not in valid_states:
            # Mapear estados del módulo hijo a mensajes claros
            state_messages = {
                'initial': 'Reserva en borrador. Complete la configuración primero.',
                'confirmed': 'Reserva confirmada. Realice check-in primero.',
                'no_show': 'Reserva marcada como No Show. No se puede facturar.',
                'cancelled': 'Reserva cancelada. No se puede facturar.'
            }
            
            message = state_messages.get(self.status_bar, 
                f"El botón Print Bill no está disponible en el estado '{self.status_bar}'")
            
            # Verificar si existe wk.wizard.message
            if self.env['wk.wizard.message'].sudo()._name:
                return self.env['wk.wizard.message'].genrated_message(
                    f"{message} El botón Print Bill solo está disponible después de confirmar la reserva.",
                    name='Estado Incorrecto'
                )
            else:
                raise UserError(f"{message} El botón Print Bill solo está disponible después de confirmar la reserva.")
        
        # Validaciones básicas antes de proceder
        if not self.check_in or not self.check_out:
            message = "Por favor complete las fechas de Check-in y Check-out antes de generar la factura."
            if self.env['wk.wizard.message'].sudo()._name:
                return self.env['wk.wizard.message'].genrated_message(message, name='Error de Validación')
            else:
                raise UserError(message)
        
        if not self.booking_line_ids:
            message = "No hay habitaciones asignadas. Agregue habitaciones antes de generar la factura."
            if self.env['wk.wizard.message'].sudo()._name:
                return self.env['wk.wizard.message'].genrated_message(message, name='Error de Validación')
            else:
                raise UserError(message)
        
        # IMPORTANTE: NO crear órdenes de venta automáticamente
        # Solo buscar las existentes como hace el módulo padre
        
        # Buscar órdenes de venta relacionadas (exactamente como el módulo padre)
        order_ids = self.env["sale.order"].search(
            [("booking_id", "=", self.id), ("state", "=", "sale")]
        )
        
        # Combinar orden principal con órdenes adicionales (exactamente como el módulo padre)
        all_orders = (self.order_id | order_ids) if self.order_id else order_ids
        
        # Si no hay órdenes, intentar crear una automáticamente (como respaldo)
        if not all_orders:
            try:
                _logger.info('No se encontraron órdenes de venta para reserva %s, intentando crear una automáticamente', self.id)
                sale_order = self._create_sale_order_for_booking()
                if sale_order:
                    # Buscar nuevamente las órdenes
                    order_ids = self.env["sale.order"].search(
                        [("booking_id", "=", self.id), ("state", "=", "sale")]
                    )
                    all_orders = (self.order_id | order_ids) if self.order_id else order_ids
                    
                    if all_orders:
                        _logger.info('Orden de venta creada automáticamente %s para reserva %s', sale_order.name, self.id)
                    else:
                        message = ("No se pudieron crear órdenes de venta automáticamente. "
                                 "Verifique que la reserva tenga todos los datos necesarios.")
                        if self.env['wk.wizard.message'].sudo()._name:
                            return self.env['wk.wizard.message'].genrated_message(message, name='Error en Creación Automática')
                        else:
                            raise UserError(message)
                else:
                    message = ("No se pudieron crear órdenes de venta automáticamente. "
                             "Verifique que la reserva tenga todos los datos necesarios.")
                    if self.env['wk.wizard.message'].sudo()._name:
                        return self.env['wk.wizard.message'].genrated_message(message, name='Error en Creación Automática')
                    else:
                        raise UserError(message)
            except Exception as e:
                _logger.error('Error creando orden de venta automática para Print Bill en reserva %s: %s', self.id, str(e))
                message = (f"Error al crear orden de venta automáticamente: {str(e)}. "
                          "Verifique que la reserva tenga todos los datos necesarios.")
                if self.env['wk.wizard.message'].sudo()._name:
                    return self.env['wk.wizard.message'].genrated_message(message, name='Error en Creación Automática')
                else:
                    raise UserError(message)
        
        # Retornar exactamente como el módulo padre
        return {
            "name": _("Booking Bill"),
            "type": "ir.actions.act_window",
            "res_model": "booking.bill",
            "view_id": self.env.ref("hotel_management_system.view_compute_bill").id,
            "view_mode": "form",
            "target": "new",
            "context": {"order_list": all_orders.ids},
        }

    def filter_booking_based_on_date(self, check_in, check_out):
        """
        Sobrescribir para evitar la validación problemática cuando estamos
        en contexto de Print Bill
        """
        # Si estamos en contexto de Print Bill, hacer una validación más permisiva
        if self.env.context.get('is_print_bill_context'):
            # Solo validar que las fechas existan, pero no hacer la validación estricta
            if not (check_in and check_out):
                return self.env["hotel.booking"]
            
            # Para Print Bill, solo verificar que no haya conflictos reales
            # pero permitir que la reserva actual pase la validación
            check_in_date = check_in.date() if hasattr(check_in, 'date') else check_in
            check_out_date = check_out.date() if hasattr(check_out, 'date') else check_out
            
            return self.filtered(
                lambda r: (
                    r.status_bar not in ("cancel", "checkout") and
                    r.check_in and r.check_out and
                    # Solo hay conflicto si las fechas se solapan realmente
                    not (r.check_out.date() <= check_in_date or 
                         r.check_in.date() >= check_out_date)
                )
            )
        
        # Si no es contexto de Print Bill, usar la lógica original del módulo padre
        return super().filter_booking_based_on_date(check_in, check_out)

    def _create_sale_order_for_booking(self):
        """
        Crear una orden de venta automática para la reserva
        """
        try:
            _logger.info('=== INICIANDO CREACIÓN DE ORDEN DE VENTA PARA RESERVA %s ===', self.id)
            
            # Validar que la reserva tenga los datos mínimos necesarios
            _logger.info('Validando datos básicos de reserva %s', self.id)
            _logger.info('Partner: %s, Check-in: %s, Check-out: %s', 
                       self.partner_id.name if self.partner_id else 'None', 
                       self.check_in, self.check_out)
            
            if not self.partner_id:
                raise ValidationError(_('La reserva debe tener un cliente asignado.'))
            
            if not self.check_in or not self.check_out:
                raise ValidationError(_('La reserva debe tener fechas de check-in y check-out válidas.'))
            
            if not self.booking_line_ids:
                raise ValidationError(_('La reserva debe tener al menos una habitación asignada.'))
            
            _logger.info('Reserva %s tiene %s líneas de habitación', self.id, len(self.booking_line_ids))
            for line in self.booking_line_ids:
                _logger.info('Línea: producto=%s, precio=%s, descuento=%s', 
                           line.product_id.name, line.price, line.discount)
            
            # Calcular los días de reserva si no están calculados
            if not hasattr(self, 'booking_days') or not self.booking_days or self.booking_days <= 0:
                try:
                    self._compute_booking_days()
                except Exception as compute_error:
                    _logger.warning('Error calculando booking_days, usando cálculo manual: %s', str(compute_error))
                    # Cálculo manual como fallback (permitir fracciones para reservas de pocas horas)
                    if self.check_in and self.check_out:
                        days_diff = (self.check_out.date() - self.check_in.date()).days
                        
                        # Si es el mismo día o diferencia pequeña, calcular en horas
                        if days_diff == 0:
                            # Mismo día: calcular duración en horas
                            if isinstance(self.check_in, datetime) and isinstance(self.check_out, datetime):
                                time_diff = self.check_out - self.check_in
                                hours = time_diff.total_seconds() / 3600.0
                                # Convertir horas a fracción de día
                                self.booking_days = max(0.01, hours / 24.0)  # Mínimo 0.01 días para visualización
                            else:
                                self.booking_days = 0.5  # Medio día por defecto
                        else:
                            # Múltiples días: calcular con precisión de horas
                            if isinstance(self.check_in, datetime) and isinstance(self.check_out, datetime):
                                time_diff = self.check_out - self.check_in
                                total_hours = time_diff.total_seconds() / 3600.0
                                self.booking_days = max(0.01, total_hours / 24.0)  # Convertir a días fraccionales
                            else:
                                self.booking_days = max(0.01, days_diff)  # Mínimo 0.01 días
                    else:
                        self.booking_days = 0.5  # Medio día por defecto
            
            _logger.info('Días de reserva calculados: %s', self.booking_days)
            
            # Preparar los datos de la orden de venta (exactamente como el módulo padre)
            order_vals = {
                'state': 'sale',  # IMPORTANTE: Crear directamente en estado 'sale' como el módulo padre
                'hotel_check_in': self.check_in,
                'booking_id': self.id,
                'partner_id': self.partner_id.id,
                'hotel_check_out': self.check_out,
                'pricelist_id': self.pricelist_id.id if self.pricelist_id else False,
                'hotel_id': self.hotel_id.id if self.hotel_id else False,
                'booking_count': 1,
            }
            
            # Crear la orden de venta
            _logger.info('Creando orden de venta con datos: %s', order_vals)
            try:
                sale_order = self.env['sale.order'].create(order_vals)
                _logger.info('Orden de venta creada exitosamente: ID=%s, Name=%s', sale_order.id, sale_order.name)
            except Exception as e:
                _logger.error('Error al crear orden de venta: %s', str(e))
                return False
            
            if not sale_order:
                _logger.error('Error: No se pudo crear la orden de venta')
                return False
            
            # Procesar cada línea de reserva para crear líneas de orden de venta (exactamente como el módulo padre)
            for line in self.booking_line_ids:
                _logger.info('Procesando línea de reserva: %s', line.product_id.name)
                
                # Preparar datos exactamente como el módulo padre
                line_data = {
                    "tax_id": line.tax_ids,
                    "order_id": sale_order.id,
                    "product_id": line.product_id.id,
                    "product_uom_qty": self.booking_days,
                    "price_unit": line.price,
                    "guest_info_ids": line.guest_info_ids if hasattr(line, 'guest_info_ids') else False,
                    "discount": line.discount,
                }
                _logger.info('Datos para crear línea de orden: %s', line_data)
                
                # Crear línea exactamente como el módulo padre
                try:
                    sale_order_line = self.env["sale.order.line"].create(line_data)
                    line.sale_order_line_id = sale_order_line.id
                    _logger.info('Línea de orden creada exitosamente: ID=%s, producto=%s, cantidad=%s', 
                               sale_order_line.id, sale_order_line.product_id.name, sale_order_line.product_uom_qty)
                except Exception as line_error:
                    _logger.error('ERROR creando línea de orden: %s', str(line_error))
                    _logger.error('Datos que causaron el error: %s', line_data)
                    raise
            
            # NUEVO: Agregar servicios adicionales a la orden de venta
            self._add_additional_services_to_sale_order(sale_order)
            
            # Verificar que las líneas se crearon correctamente
            _logger.info('Orden de venta %s tiene %s líneas después de la creación', 
                       sale_order.id, len(sale_order.order_line))
            
            # IMPORTANTE: La orden se crea directamente en estado 'sale' como el módulo padre
            # No es necesario llamar action_confirm() porque ya está confirmada
            
            # Actualizar la reserva con la orden de venta creada
            self.write({'order_id': sale_order.id})
            
            # Crear mensaje de seguimiento
            booking_days = getattr(self, 'booking_days', 1)  # Usar 1 como valor por defecto si no existe booking_days
            self.message_post(
                body=_('Orden de venta creada y confirmada automáticamente con %s días de reserva.') % booking_days,
                subject=_('Orden de Venta Creada')
            )
            
            return sale_order
            
        except Exception as e:
            _logger.error('Error creating sale order for booking %s: %s', self.id, str(e))
            # Crear mensaje de error más detallado
            self.message_post(
                body=_('Error al crear orden de venta: %s') % str(e),
                subject=_('Error en Creación de Orden de Venta'),
                message_type='comment'
            )
            return False
    
    def _add_additional_services_to_sale_order(self, sale_order):
        """
        Agregar servicios adicionales (early check-in, late check-out, servicios manuales)
        a la orden de venta para que se facturen correctamente
        """
        self.ensure_one()
        _logger.info('=== AGREGANDO SERVICIOS ADICIONALES A ORDEN DE VENTA %s ===', sale_order.name)
        
        services_added = 0
        
        # 1. EARLY CHECK-IN SERVICE
        if self.early_checkin_charge and self.early_checkin_charge > 0:
            early_checkin_product = self._get_or_create_service_product(
                'Early Check-in', 
                'Servicio de ingreso anticipado'
            )
            
            if early_checkin_product:
                try:
                    self.env['sale.order.line'].create({
                        'order_id': sale_order.id,
                        'product_id': early_checkin_product.id,
                        'name': 'Early Check-in',
                        'product_uom_qty': 1,
                        'price_unit': self.early_checkin_charge,
                        'tax_id': [(6, 0, early_checkin_product.taxes_id.ids)],
                    })
                    services_added += 1
                    _logger.info('✅ Early Check-in agregado: %s', self.early_checkin_charge)
                except Exception as e:
                    _logger.error('❌ Error agregando Early Check-in: %s', str(e))
        
        # 2. LATE CHECK-OUT SERVICE
        if self.late_checkout_charge and self.late_checkout_charge > 0:
            late_checkout_product = self._get_or_create_service_product(
                'Late Check-out', 
                'Servicio de salida tardía'
            )
            
            if late_checkout_product:
                try:
                    self.env['sale.order.line'].create({
                        'order_id': sale_order.id,
                        'product_id': late_checkout_product.id,
                        'name': 'Late Check-out',
                        'product_uom_qty': 1,
                        'price_unit': self.late_checkout_charge,
                        'tax_id': [(6, 0, late_checkout_product.taxes_id.ids)],
                    })
                    services_added += 1
                    _logger.info('✅ Late Check-out agregado: %s', self.late_checkout_charge)
                except Exception as e:
                    _logger.error('❌ Error agregando Late Check-out: %s', str(e))
        
        # 3. SERVICIOS MANUALES
        manual_services = self.hotel_service_lines.filtered(
            lambda s: s.service_id and s.service_id.name == 'Servicio Manual' and s.amount > 0
        )
        
        for service_line in manual_services:
            manual_service_product = self._get_or_create_service_product(
                'Servicio Manual', 
                service_line.note or 'Servicio adicional'
            )
            
            if manual_service_product:
                try:
                    self.env['sale.order.line'].create({
                        'order_id': sale_order.id,
                        'product_id': manual_service_product.id,
                        'name': service_line.note or 'Servicio Manual',
                        'product_uom_qty': 1,
                        'price_unit': service_line.amount,
                        'tax_id': [(6, 0, manual_service_product.taxes_id.ids)],
                    })
                    services_added += 1
                    _logger.info('✅ Servicio manual agregado: %s - %s', service_line.note, service_line.amount)
                except Exception as e:
                    _logger.error('❌ Error agregando servicio manual: %s', str(e))
        
        # 4. OTROS SERVICIOS DEL HOTEL (si existen)
        other_services = self.hotel_service_lines.filtered(
            lambda s: s.service_id and s.service_id.name != 'Servicio Manual' and s.amount > 0
        )
        
        for service_line in other_services:
            # Intentar usar el producto del servicio directamente si es posible
            service_product = None
            
            # Si el servicio tiene un producto asociado, usarlo
            if hasattr(service_line.service_id, 'product_id') and service_line.service_id.product_id:
                service_product = service_line.service_id.product_id
            else:
                # Crear o buscar producto para este servicio
                service_product = self._get_or_create_service_product(
                    service_line.service_id.name,
                    service_line.note or service_line.service_id.name
                )
            
            if service_product:
                try:
                    self.env['sale.order.line'].create({
                        'order_id': sale_order.id,
                        'product_id': service_product.id,
                        'name': service_line.note or service_line.service_id.name,
                        'product_uom_qty': 1,
                        'price_unit': service_line.amount,
                        'tax_id': [(6, 0, service_product.taxes_id.ids)],
                    })
                    services_added += 1
                    _logger.info('✅ Servicio hotel agregado: %s - %s', service_line.service_id.name, service_line.amount)
                except Exception as e:
                    _logger.error('❌ Error agregando servicio hotel: %s', str(e))
        
        _logger.info('=== SERVICIOS ADICIONALES COMPLETADOS: %s servicios agregados ===', services_added)
        
        # Actualizar mensaje en el chatter
        if services_added > 0:
            self.message_post(
                body=_('✅ %s servicios adicionales agregados automáticamente a la orden de venta %s') % (
                    services_added, sale_order.name
                ),
                subject=_('Servicios Adicionales Agregados')
            )
        
        return services_added
    
    def _get_or_create_service_product(self, service_name, description):
        """
        Obtener o crear un producto de servicio para facturación
        """
        # Buscar producto existente
        existing_product = self.env['product.product'].search([
            ('name', '=', service_name),
            ('type', '=', 'service'),
            ('sale_ok', '=', True)
        ], limit=1)
        
        if existing_product:
            return existing_product
        
        # Crear nuevo producto si no existe
        try:
            new_product = self.env['product.product'].create({
                'name': service_name,
                'type': 'service',
                'sale_ok': True,
                'purchase_ok': False,
                'list_price': 0.0,  # El precio se establece en la línea de venta
                'description': description,
                'categ_id': self._get_service_category().id,
            })
            _logger.info('✅ Producto de servicio creado: %s', service_name)
            return new_product
            
        except Exception as e:
            _logger.error('❌ Error creando producto de servicio %s: %s', service_name, str(e))
            return None
    
    def _get_service_category(self):
        """
        Obtener o crear categoría para servicios de hotel
        """
        # Buscar categoría existente
        service_category = self.env['product.category'].search([
            ('name', '=', 'Servicios de Hotel')
        ], limit=1)
        
        if service_category:
            return service_category
        
        # Crear categoría si no existe
        try:
            service_category = self.env['product.category'].create({
                'name': 'Servicios de Hotel',
                'parent_id': False,
            })
            _logger.info('✅ Categoría de servicios creada: Servicios de Hotel')
            return service_category
            
        except Exception as e:
            _logger.error('❌ Error creando categoría de servicios: %s', str(e))
            # Usar categoría por defecto
            return self.env['product.category'].search([], limit=1) or self.env['product.category']
    
    def update_existing_sale_orders_with_services(self):
        """
        Actualizar órdenes de venta existentes agregando servicios faltantes
        Útil para reservas que ya tienen órdenes pero les faltan servicios
        """
        self.ensure_one()
        _logger.info('=== ACTUALIZANDO ÓRDENES EXISTENTES CON SERVICIOS FALTANTES ===')
        
        # Buscar todas las órdenes relacionadas
        all_orders = self.env['sale.order'].search([
            ('booking_id', '=', self.id),
            ('state', 'in', ['draft', 'sent', 'sale'])
        ])
        
        if self.order_id and self.order_id not in all_orders:
            all_orders |= self.order_id
        
        if not all_orders:
            _logger.warning('No se encontraron órdenes de venta para actualizar en reserva %s', self.id)
            return 0
        
        total_services_added = 0
        
        for order in all_orders:
            _logger.info('Actualizando orden %s', order.name)
            
            # Verificar qué servicios ya existen en la orden
            existing_service_names = set(order.order_line.mapped('name'))
            
            services_to_add = []
            
            # Early Check-in
            if (self.early_checkin_charge and self.early_checkin_charge > 0 and
                'Early Check-in' not in existing_service_names):
                services_to_add.append({
                    'name': 'Early Check-in',
                    'amount': self.early_checkin_charge,
                    'description': 'Servicio de ingreso anticipado'
                })
            
            # Late Check-out
            if (self.late_checkout_charge and self.late_checkout_charge > 0 and
                'Late Check-out' not in existing_service_names):
                services_to_add.append({
                    'name': 'Late Check-out',
                    'amount': self.late_checkout_charge,
                    'description': 'Servicio de salida tardía'
                })
            
            # Servicios manuales
            manual_services = self.hotel_service_lines.filtered(
                lambda s: s.service_id and s.service_id.name == 'Servicio Manual' and s.amount > 0
            )
            
            for service_line in manual_services:
                service_name = service_line.note or 'Servicio Manual'
                if service_name not in existing_service_names:
                    services_to_add.append({
                        'name': service_name,
                        'amount': service_line.amount,
                        'description': service_line.note or 'Servicio adicional'
                    })
            
            # Agregar servicios faltantes
            for service_info in services_to_add:
                service_product = self._get_or_create_service_product(
                    service_info['name'], 
                    service_info['description']
                )
                
                if service_product:
                    try:
                        self.env['sale.order.line'].create({
                            'order_id': order.id,
                            'product_id': service_product.id,
                            'name': service_info['name'],
                            'product_uom_qty': 1,
                            'price_unit': service_info['amount'],
                            'tax_id': [(6, 0, service_product.taxes_id.ids)],
                        })
                        total_services_added += 1
                        _logger.info('✅ Servicio agregado a orden %s: %s - %s', 
                                   order.name, service_info['name'], service_info['amount'])
                    except Exception as e:
                        _logger.error('❌ Error agregando servicio %s a orden %s: %s', 
                                    service_info['name'], order.name, str(e))
        
        if total_services_added > 0:
            self.message_post(
                body=_('✅ %s servicios adicionales agregados a órdenes de venta existentes') % total_services_added,
                subject=_('Órdenes Actualizadas con Servicios')
            )
        
        _logger.info('=== ACTUALIZACIÓN COMPLETADA: %s servicios agregados ===', total_services_added)
        return total_services_added
    
    def action_sync_services_to_sale_orders(self):
        """
        Acción del botón para sincronizar servicios con órdenes de venta
        """
        self.ensure_one()
        
        try:
            services_added = self.update_existing_sale_orders_with_services()
            
            if services_added > 0:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Sincronización Exitosa'),
                        'message': _('✅ %s servicios adicionales sincronizados con las órdenes de venta') % services_added,
                        'type': 'success',
                        'sticky': True,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Sincronización Completada'),
                        'message': _('ℹ️ Todos los servicios ya están sincronizados con las órdenes de venta'),
                        'type': 'info',
                        'sticky': False,
                        
                    }
                }
                
        except Exception as e:
            _logger.error('Error en sincronización de servicios para reserva %s: %s', self.id, str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error en Sincronización'),
                    'message': _('❌ Error al sincronizar servicios: %s') % str(e),
                    'type': 'danger',
                    'sticky': False,
                }
            }
    
    # =============================================================================
    # MÉTODOS DE SOPORTE
    # =============================================================================
    
    def _process_checkout_services(self):
        """Procesar servicios durante el checkout"""
        try:
            # Replicar la funcionalidad del método base si existe
            if hasattr(super(), 'manage_alloted_services'):
                res = self.manage_alloted_services()
                if res:
                    return res

            # Configuración de facturación automática
            auto_invoice = self.env["ir.config_parameter"].sudo().get_param(
                "hotel_management_system.auto_invoice_gen"
            )
            if auto_invoice and hasattr(self, 'create_invoice'):
                self.create_invoice()

            # Configuración de feedback
            feedback_config = self.env["ir.config_parameter"].sudo().get_param(
                "hotel_management_system.feedback_config"
            )
            if feedback_config == "at_checkout" and hasattr(self, 'send_feedback_btn'):
                self.send_feedback_btn()

            # Configuración de facturación de agente
            auto_bill = self.env["ir.config_parameter"].sudo().get_param(
                "hotel_management_system.auto_bill_gen"
            )
            if (auto_bill and hasattr(self, 'via_agent') and self.via_agent 
                and hasattr(self, 'create_agent_bill')):
                self.create_agent_bill()

            # Configuración de housekeeping
            hk_mode = self.env["ir.config_parameter"].sudo().get_param(
                "hotel_management_system.housekeeping_config"
            )
            if hk_mode in ["at_checkout", "both"] and hasattr(self, 'create_housekeeping'):
                self.create_housekeeping()

            # Configuración de email de check-out
            email_on_checkout = self.env["ir.config_parameter"].sudo().get_param(
                "hotel_management_system.send_on_checkout"
            )
            if email_on_checkout and hasattr(self, 'send_checkout_email'):
                self.send_checkout_email()
            
        except Exception as e:
            _logger.warning('Error processing checkout services: %s', str(e))
    
    def _release_rooms(self):
        """Liberar habitaciones asignadas"""
        for line in self.booking_line_ids:
            if hasattr(line.product_id, 'room_status'):
                line.product_id.room_status = 'available'
    
    def _apply_no_show_policy(self):
        """Aplicar política de no show"""
        # Implementar lógica de penalización por no show
        # Esto dependerá de las políticas específicas del hotel
        pass
    
    # =============================================================================
    # VALIDACIONES Y CONSTRAINTS
    # =============================================================================
    
    @api.constrains('status_bar', 'booking_line_ids')
    def _check_room_assignment_consistency(self):
        """Validar consistencia entre estado y asignación de habitaciones"""
        # Saltar validación si estamos en proceso de cambio de habitación
        if self.env.context.get('skip_room_validation'):
            return
            
        for record in self:
            state_info = BOOKING_STATES.get(record.status_bar, {})
            requires_room = state_info.get('requires_room', False)
            
            if requires_room and not record.booking_line_ids:
                raise ValidationError(_(
                    'El estado "%s" requiere que haya habitaciones asignadas'
                ) % state_info.get('name', record.status_bar))
    
    @api.constrains('status_bar', 'check_in', 'check_out')
    def _check_date_consistency(self):
        """Validar consistencia de fechas con el estado"""
        for record in self:
            if record.status_bar in ['checkin', 'checkout']:
                if not record.check_in:
                    raise ValidationError(_('Debe especificar fecha de check-in'))
                
                if record.status_bar == 'checkout' and not record.check_out:
                    raise ValidationError(_('Debe especificar fecha de check-out'))
    
    def write(self, vals):
        """
        Sobrescribir write para agregar validación de fecha de check-in
        """
        # COMENTADO TEMPORALMENTE PARA PRUEBAS
        # Validar cambio de estado a check-in
        # if 'status_bar' in vals and vals['status_bar'] == 'checkin':
        #     for record in self:
        #         # Validar que la fecha de check-in sea hoy o en el pasado
        #         today = fields.Date.today()
        #         
        #         # Obtener la fecha de check-in (puede venir en vals o estar en el record)
        #         check_in_date = vals.get('check_in', record.check_in)
        #         
        #         # Manejo robusto de fechas para Odoo 17
        #         if check_in_date:
        #             if isinstance(check_in_date, datetime):
        #                 check_in_date = check_in_date.date()
        #             elif isinstance(check_in_date, str):
        #                 check_in_date = fields.Date.from_string(check_in_date)
        #             
        #             if check_in_date and check_in_date > today:
        #                 raise UserError(_('No se puede realizar check-in antes de la fecha programada.'))
        
        return super().write(vals)
    
    # =============================================================================
    # MÉTODOS DE COMPATIBILIDAD CON MÓDULO BASE
    # =============================================================================

    # =============================================================================    
    # MÉTODOS DE UTILIDAD
    # =============================================================================
    def get_state_info(self):
        """Obtener información completa del estado actual"""
        self.ensure_one()
        current_state = self.status_bar or BookingState.INITIAL
        return BOOKING_STATES.get(current_state, {})
    
    def get_available_transitions_info(self):
        """Obtener información detallada de transiciones disponibles"""
        self.ensure_one()
        current_state = self.status_bar or BookingState.INITIAL
        transitions = StateTransitionValidator.get_available_transitions(current_state)
        
        return [{
            'state': state,
            'name': BOOKING_STATES.get(state, {}).get('name', state),
            'description': BOOKING_STATES.get(state, {}).get('description', ''),
            'color': BOOKING_STATES.get(state, {}).get('color', 'secondary')
        } for state in transitions]
    
    def is_state_terminal(self):
        """Verificar si el estado actual es terminal"""
        self.ensure_one()
        current_state = self.status_bar or BookingState.INITIAL
        return BOOKING_STATES.get(current_state, {}).get('is_terminal', False)
    
    def force_compute_original_price(self):
        """
        Método para forzar el recálculo del precio original
        Útil para corregir reservas existentes con precio original en 0
        """
        self.ensure_one()
        
        # Forzar recálculo
        self._compute_original_price()
        
        # Log del resultado
        _logger.info(
            'Booking %s: Forced original price computation. Result: %s (from %s lines)',
            self.id, self.original_price, len(self.booking_line_ids)
        )
        
        return self.original_price
    
    @api.model
    def fix_zero_original_prices(self):
        """
        Método utilitario para corregir reservas existentes con precio original en 0
        Se puede ejecutar desde código o desde un botón de administración
        """
        # Buscar reservas con precio original en 0 pero que tienen líneas de reserva
        problematic_bookings = self.search([
            ('original_price', '=', 0),
            ('booking_line_ids', '!=', False)
        ])
        
        fixed_count = 0
        for booking in problematic_bookings:
            old_price = booking.original_price
            booking.force_compute_original_price()
            
            if booking.original_price > 0:
                fixed_count += 1
                _logger.info(
                    'Fixed booking %s: original_price %s -> %s',
                    booking.id, old_price, booking.original_price
                )
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Corrección Completada'),
                'message': _('Se corrigieron %s reservas con precio original en 0.') % fixed_count,
                'type': 'success',
            }
        }

    def action_add_rooms_with_context(self):
        """
        Versión personalizada de action_add_rooms que usa el contexto para pre-llenar la habitación
        """
        self.ensure_one()
        
        # Asegurar que booking_days esté calculado en la reserva principal
        if not self.booking_days and self.check_in and self.check_out:
            self._compute_booking_days()
        
        # Obtener el ID de la habitación del contexto
        default_product_id = self.env.context.get('default_product_id')
        
        # Obtener habitaciones disponibles
        booking = self.env["hotel.booking"].search([])
        product_ids = self.env["product.product"].search([('product_tmpl_id.hotel_id', '!=', self.hotel_id.id)])

        for line in booking:
            filtered_bookings = line.filter_booking_based_on_date(self.check_in, self.check_out)
            if filtered_bookings:
                product_ids += line.mapped("booking_line_ids.product_id")

        # Si hay una habitación específica en el contexto, filtrar solo esa
        if default_product_id:
            product_ids = self.env["product.product"].browse(default_product_id)

        # Crear el contexto para el formulario de línea de reserva
        line_context = {
            'default_booking_id': self.id,
            'default_product_ids': product_ids.ids,
            'is_add_rooms_modal': True,  # Marcar que es el modal de Add Rooms
            'default_booking_days': self.booking_days or 1,  # Usar 1 como valor por defecto si no hay días
        }
        
        # Agregar la habitación específica si está disponible
        if default_product_id:
            line_context['default_product_id'] = default_product_id
            
        # Agregar datos del huésped para pre-llenar Members Details
        if self.partner_id:
            line_context['default_guest_name'] = self.partner_id.name
            line_context['default_guest_email'] = self.partner_id.email or ''
            line_context['default_guest_phone'] = self.partner_id.phone or ''
            # Pasar el partner_id para el selector de contactos
            line_context['default_partner_id'] = self.partner_id.id

        # Usar una vista genérica si no existe la específica
        try:
            view_id = self.env.ref('hotel_management_system_extension.view_hotel_booking_line_form_extension').id
        except Exception:
            # Fallback a vista estándar si no existe la personalizada
            view_id = False

        return {
            'name': _('Add Rooms'),
            'type': 'ir.actions.act_window',
            'res_model': 'hotel.booking.line',
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'new',
            'context': line_context,
        }


class HotelBookingLineExtension(models.Model):
    _inherit = 'hotel.booking.line'
    
    # Sobrescribir el campo booking_days para usar nuestro método de cálculo
    # Cambiado a Float para permitir reservas de pocas horas (fracciones de día)
    booking_days = fields.Float(
        string="Days Book For", 
        compute="_compute_booking_days_from_booking",
        store=True,
        copy=False,
        digits=(16, 4),  # Permitir hasta 4 decimales para precisión en horas
        help="Días de reserva (puede ser fraccional para reservas de pocas horas, ej: 0.08 = 2 horas)"
    )
    
    # =============================================================================
    # CAMPOS DE DESCUENTO
    # =============================================================================
    
    # Precio original de la habitación, para no perderlo
    original_price = fields.Monetary(
        string="Precio Original", 
        readonly=True, 
        tracking=True,
        currency_field='currency_id',
        help="Precio original de la habitación antes de cualquier descuento"
    )
    
    # Monto del descuento aplicado
    discount_amount = fields.Monetary(
        string="Monto Descontado", 
        readonly=True, 
        tracking=True,
        currency_field='currency_id',
        help="Monto total del descuento aplicado a la línea de reserva"
    )
    
    # Razón del descuento
    discount_reason = fields.Text(
        string="Razón del Descuento/Cambio", 
        tracking=True,
        help="Explicación del motivo del descuento o cambio de precio"
    )
    
    # Campo temporal para controlar el wizard
    _need_price_wizard = fields.Boolean(
        string="Necesita Wizard de Precio",
        default=False,
        help="Campo temporal para controlar la apertura del wizard de cambio de precio"
    )
    
    # Campos para cambio de habitación
    is_room_change_segment = fields.Boolean(
        string="Room Change Segment",
        default=False,
        help="Indicates this line is part of a room change"
    )
    
    previous_line_id = fields.Many2one(
        'hotel.booking.line',
        string="Previous Line",
        help="Previous booking line in the room change sequence"
    )
    
    next_line_id = fields.Many2one(
        'hotel.booking.line',
        string="Next Line",
        help="Next booking line in the room change sequence"
    )
    
    
    @api.depends('booking_id.booking_days', 'booking_id.check_in', 'booking_id.check_out')
    def _compute_booking_days_from_booking(self):
        """
        Calcular booking_days basado en la reserva principal
        """
        for line in self:
            if not line.booking_id:
                line.booking_days = 0
                continue
                
            # Si la reserva principal ya tiene booking_days calculado, usarlo
            if line.booking_id.booking_days and line.booking_id.booking_days > 0:
                line.booking_days = line.booking_id.booking_days
                continue
            
            # Si no, calcular desde las fechas
            if line.booking_id.check_in and line.booking_id.check_out:
                try:
                    check_in = line.booking_id.check_in
                    check_out = line.booking_id.check_out
                    
                    # Convertir a datetime si es necesario
                    if isinstance(check_in, str):
                        check_in = fields.Datetime.from_string(check_in)
                    if isinstance(check_out, str):
                        check_out = fields.Datetime.from_string(check_out)
                    
                    # Calcular días (permitir fracciones para reservas de pocas horas)
                    if hasattr(check_in, 'date') and hasattr(check_out, 'date'):
                        # Calcular diferencia en días completos
                        days_diff = (check_out.date() - check_in.date()).days
                        
                        # Si es el mismo día o diferencia pequeña, calcular en horas
                        if days_diff == 0:
                            # Mismo día: calcular duración en horas y convertir a fracción de día
                            if isinstance(check_in, datetime) and isinstance(check_out, datetime):
                                time_diff = check_out - check_in
                                hours = time_diff.total_seconds() / 3600.0
                                # Convertir horas a fracción de día (24 horas = 1 día)
                                line.booking_days = max(0.01, hours / 24.0)  # Mínimo 0.01 días (14.4 minutos) para visualización
                            else:
                                line.booking_days = 0.5  # Medio día por defecto si no se puede calcular
                        else:
                            # Múltiples días: calcular con precisión de horas
                            if isinstance(check_in, datetime) and isinstance(check_out, datetime):
                                time_diff = check_out - check_in
                                total_hours = time_diff.total_seconds() / 3600.0
                                line.booking_days = max(0.01, total_hours / 24.0)  # Convertir a días fraccionales
                            else:
                                line.booking_days = max(0.01, days_diff)  # Mínimo 0.01 días
                    else:
                        line.booking_days = 0.5  # Medio día por defecto
                except Exception:
                    line.booking_days = 0
            else:
                line.booking_days = 0
    
    @api.depends('price', 'discount', 'tax_ids', 'booking_days', 'booking_id.currency_id')
    def _compute_amount_extension(self):
        """
        Sobrescribir el cálculo de amount para asegurar que funcione correctamente
        """
        for line in self:
            # Asegurar que booking_days esté calculado
            if not line.booking_days and line.booking_id:
                line._compute_booking_days_from_booking()
            
            # El precio (line.price) es el precio por noche (new_price)
            # El cálculo es simple: precio por noche * días de reserva
            # NO aplicar descuento adicional porque new_price ya es el precio final por noche
            price_per_night = line.price or 0.0
            
            # Calcular impuestos
            if line.tax_ids and line.booking_id and line.booking_id.currency_id:
                taxes = line.tax_ids.compute_all(
                    price_per_night,
                    line.booking_id.currency_id,
                    1,
                    product=line.product_id,
                )
                line.subtotal_price = taxes["total_excluded"] * line.booking_days
                line.taxed_price = taxes["total_included"] * line.booking_days
            else:
                # Si no hay impuestos, usar el precio directo
                line.subtotal_price = price_per_night * line.booking_days
                line.taxed_price = price_per_night * line.booking_days
    
    def _compute_amount(self):
        """
        Sobrescribir el método original para usar nuestra lógica mejorada
        """
        self._compute_amount_extension()
    
    @api.onchange('booking_days')
    def _onchange_booking_days(self):
        """
        Recalcular el subtotal cuando cambia booking_days
        """
        if self.booking_days and self.booking_days > 0.0 and self.price:
            self._compute_amount()
    
    @api.onchange('price', 'discount', 'tax_ids')
    def _onchange_price_discount_taxes(self):
        """
        Recalcular el subtotal cuando cambian precio, descuento o impuestos
        """
        if self.price and self.booking_days and self.booking_days > 0.0:
            self._compute_amount()
    
    @api.onchange('product_id')
    def _onchange_product_id_set_original_price(self):
        """
        Establecer el precio original cuando se selecciona una habitación
        """
        if self.product_id:
            # Usar el precio de lista del template del producto como precio original
            if self.product_id.product_tmpl_id:
                original_price = self.product_id.product_tmpl_id.list_price or 0
                if original_price > 0:
                    self.original_price = original_price
                    # Si no hay precio establecido, usar el precio original
                    if not self.price:
                        self.price = original_price
                else:
                    # Fallback al precio del producto si el template no tiene precio
                    product_price = self.product_id.list_price or 0
                    if product_price > 0:
                        self.original_price = product_price
                        if not self.price:
                            self.price = product_price
    
    @api.onchange('price')
    def _onchange_price_calculate_discount(self):
        """
        Calcular descuento cuando se cambia el precio manualmente
        """
        if self.original_price > 0 and self.price:
            if self.price < self.original_price:
                # Si el nuevo precio es menor, calcula el descuento
                self.discount_amount = self.original_price - self.price
                # Si no hay razón especificada, usar una por defecto
                if not self.discount_reason:
                    self.discount_reason = "Descuento manual aplicado"
            elif self.price > self.original_price:
                # Si el precio es mayor, no hay descuento
                self.discount_amount = 0.0
                if not self.discount_reason:
                    self.discount_reason = "Precio aumentado manualmente"
            else:
                # Si el precio es igual al original, no hay descuento
                self.discount_amount = 0.0
                if not self.discount_reason:
                    self.discount_reason = ""
    
    
    
    
    
    def action_open_price_change_wizard(self):
        """
        Abrir wizard para capturar motivo del cambio de precio
        """
        self.ensure_one()
        
        # Guardar el precio original si no está establecido
        if not self.original_price and self.price:
            self.original_price = self.price
        
        # Calcular precio original robusto si no está disponible
        if not self.original_price or self.original_price == 0:
            # Intentar calcular usando lista de precios
            if self.booking_id and self.booking_id.pricelist_id and self.product_id:
                try:
                    pricelist = self.booking_id.pricelist_id
                    partner = self.booking_id.partner_id
                    date = self.booking_id.check_in or fields.Date.today()
                    
                    pricelist_price = pricelist.get_product_price(
                        self.product_id,
                        1,
                        partner=partner,
                        date=date,
                        uom_id=self.product_id.uom_id.id
                    )
                    
                    if pricelist_price and pricelist_price > 0:
                        self.original_price = pricelist_price
                except Exception:
                    # Fallback al precio de lista del producto
                    if self.product_id.product_tmpl_id.list_price:
                        self.original_price = self.product_id.product_tmpl_id.list_price
                    elif self.product_id.list_price:
                        self.original_price = self.product_id.list_price
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cambio de Precio - %s') % (self.product_id.name or 'Habitación'),
            'res_model': 'hotel.booking.line.price.change.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_booking_line_id': self.id,
                'booking_line_id': self.id,  # Para compatibilidad con el wizard
                'default_original_price': self.original_price or self.price,
                'default_new_price': self.price,
            },
        }
    
    @api.onchange('discount_reason')
    def _onchange_discount_reason_validation(self):
        """
        Validar que si hay descuento, debe haber una razón
        """
        if self.discount_amount > 0 and not self.discount_reason:
            return {
                'warning': {
                    'title': _('Razón de Descuento Requerida'),
                    'message': _('Por favor especifique la razón del descuento aplicado.')
                }
            }
    
    def write(self, vals):
        """
        Sobrescribir write para manejar cambios en campos calculados
        """
        result = super().write(vals)
        
        # Solo recalcular si es necesario y no viene del modal
        if (not self.env.context.get('is_add_rooms_modal') and 
            any(field in vals for field in ['price', 'discount', 'tax_ids'])):
            for line in self:
                if line.booking_id and line.price:
                    # Solo recalcular si hay datos válidos
                    line._compute_amount()
        
        return result
    
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribir create para crear automáticamente la reserva principal
        cuando se crea una línea desde el Gantt
        """
        # Crear las líneas primero
        lines = super().create(vals_list)
        
        # Solo crear reserva automáticamente si viene del Gantt
        # NO crear automáticamente si está en el modal de Add Rooms
        if (self.env.context.get('from_gantt') and 
            not self.env.context.get('is_add_rooms_modal')):
            for line in lines:
                if not line.booking_id:
                    line._create_booking_from_gantt()
        
        return lines
    
    @api.model
    def default_get(self, fields_list):
        """
        Sobrescribir default_get para pre-llenar Members Details con datos del huésped principal
        """
        res = super().default_get(fields_list)
        
        # Solo aplicar si estamos en el contexto del modal Add Rooms
        if self.env.context.get('is_add_rooms_modal'):
            guest_name = self.env.context.get('default_guest_name')
            guest_email = self.env.context.get('default_guest_email')
            guest_phone = self.env.context.get('default_guest_phone')
            partner_id = self.env.context.get('default_partner_id')
            
            # Establecer booking_days desde el contexto
            if 'booking_days' in fields_list:
                res['booking_days'] = self.env.context.get('default_booking_days', 1)
            
            # Si tenemos datos del huésped, crear un registro guest_info por defecto
            if guest_name and 'guest_info_ids' in fields_list:
                # Crear datos por defecto para guest_info_ids
                guest_info_vals = {
                    'name': guest_name,
                    'age': 30,  # Edad por defecto
                    'gender': 'male',  # Género por defecto
                }
                
                # Si hay un partner_id, incluirlo
                if partner_id:
                    guest_info_vals['partner_id'] = partner_id
                
                # Agregar el registro guest_info por defecto
                res['guest_info_ids'] = [(0, 0, guest_info_vals)]
        
        return res
    
    def _create_booking_from_gantt(self):
        """
        Crear la reserva principal desde datos temporales del Gantt
        """
        self.ensure_one()
        
        # Obtener datos temporales del contexto
        temp_check_in = self.env.context.get('temp_check_in')
        temp_check_out = self.env.context.get('temp_check_out')
        temp_hotel_id = self.env.context.get('temp_hotel_id')
        temp_user_id = self.env.context.get('temp_user_id')
        temp_partner_id = self.env.context.get('temp_partner_id')
        
        if temp_check_in and temp_check_out:  # Solo crear si hay fechas
            booking_vals = {
                'partner_id': temp_partner_id or False,
                'check_in': temp_check_in,
                'check_out': temp_check_out,
                'hotel_id': temp_hotel_id or False,
                'user_id': temp_user_id or self.env.user.id,
                'status_bar': 'initial',  # Estado inicial
                'company_id': self.env.company.id,
                'currency_id': self.env.company.currency_id.id,
            }
            
            # Crear la reserva principal
            new_booking = self.env['hotel.booking'].create(booking_vals)
            
            # Asignar la línea a la nueva reserva
            self.write({'booking_id': new_booking.id})
            
            # Crear mensaje de seguimiento
            new_booking.message_post(
                body=_('Reserva creada desde Gantt - Línea de habitación.'),
                subject=_('Reserva Creada desde Gantt')
            )
            
            return new_booking
        
        return False

    def action_cancel_add_rooms(self):
        """
        Método para manejar la cancelación del modal de Add Rooms
        Elimina cualquier línea de reserva creada temporalmente
        """
        # Buscar líneas de reserva sin booking_id (temporales) creadas recientemente por el usuario actual
        temp_lines = self.search([
            ('booking_id', '=', False),
            ('create_uid', '=', self.env.user.id),
            ('create_date', '>=', fields.Datetime.now() - timedelta(minutes=5))
        ])
        
        # Eliminar las líneas temporales
        if temp_lines:
            temp_lines.unlink()
        
        return {
            'type': 'ir.actions.act_window_close'
        }

    def action_open_change_room_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Change Room'),
            'res_model': 'hotel.booking.line.change.room.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_booking_line_id': self.id,
                'default_booking_id': self.booking_id.id,
            }
        }
    
    def action_request_cleaning(self):
        """Acción específica para solicitar limpieza después del checkout desde booking line"""
        self.ensure_one()
        if self.booking_id and self.booking_id.status_bar == 'checkout':
            self.booking_id.status_bar = 'cleaning_needed'
            # Agregar mensaje en el chatter
            self.booking_id.message_post(
                body=f"Limpieza solicitada después del checkout por {self.env.user.name}",
                message_type='notification'
            )
        return True


class ProductTemplateExtension(models.Model):
    _inherit = 'product.template'
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribir create para marcar automáticamente habitaciones nuevas como listas
        """
        # Crear el producto template primero
        products = super().create(vals_list)
        
        # Para cada producto template creado, verificar si es una habitación
        for product in products:
            if hasattr(product, 'is_room_type') and product.is_room_type:
                # Marcar la habitación como lista automáticamente
                product._mark_new_room_template_as_ready()
        
        return products
    
    def _mark_new_room_template_as_ready(self):
        """
        Marcar una habitación nueva como lista (ROOM_READY)
        """
        self.ensure_one()
        
        # Solo procesar si es una habitación
        if not hasattr(self, 'is_room_type') or not self.is_room_type:
            return
        
        # Crear un mensaje de seguimiento
        self.message_post(
            body=_('Habitación nueva creada automáticamente marcada como lista (ROOM_READY). Disponible para reservas inmediatamente.'),
            subject=_('Habitación Nueva - Lista')
        )
        
        # Log para debugging
        _logger.info(
            'Habitación nueva (template) %s (ID: %s) marcada automáticamente como ROOM_READY',
            self.name, self.id
        )
        
        return True


class ProductExtension(models.Model):
    _inherit = 'product.product'
    
    # Campo para el estado de la habitación
    room_status = fields.Selection([
        ('available', 'Disponible'),
        ('occupied', 'Ocupada'),
        ('cleaning', 'En Limpieza'),
        ('maintenance', 'En Mantenimiento'),
        ('blocked', 'Bloqueada'),
    ], string='Estado de Habitación', default='available', tracking=True)
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribir create para marcar automáticamente habitaciones nuevas como listas
        """
        # Crear el producto primero
        products = super().create(vals_list)
        
        # Para cada producto creado, verificar si es una habitación
        for product in products:
            if hasattr(product, 'is_room_type') and product.is_room_type:
                # Marcar la habitación como lista automáticamente
                product._mark_new_room_as_ready()
        
        return products
    
    def _mark_new_room_as_ready(self):
        """
        Marcar una habitación nueva como lista (ROOM_READY)
        """
        self.ensure_one()
        
        # Solo procesar si es una habitación
        if not hasattr(self, 'is_room_type') or not self.is_room_type:
            return
        
        # Marcar como disponible automáticamente
        self.room_status = 'available'
        
        # Crear un mensaje de seguimiento
        self.message_post(
            body=_('Habitación nueva creada automáticamente marcada como lista (ROOM_READY). Disponible para reservas inmediatamente.'),
            subject=_('Habitación Nueva - Lista')
        )
        
        # Log para debugging
        _logger.info(
            'Habitación nueva %s (ID: %s) marcada automáticamente como ROOM_READY',
            self.name, self.id
        )
        
        return True


# Agregar método auxiliar para transferencia de datos en cambios de habitación
class HotelBookingDataTransfer(models.Model):
    _inherit = 'hotel.booking'
    
    def copy_all_data_to_booking(self, target_booking):
        """
        Método auxiliar para copiar toda la información relevante a otra reserva
        Útil para cambios de habitación y transferencias
        """
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info('=== COPIANDO DATOS COMPLETOS ENTRE RESERVAS ===')
        
        # 1. Copiar servicios manuales
        services_copied = 0
        for service_line in self.hotel_service_lines:
            if service_line.service_id and service_line.service_id.name == 'Servicio Manual':
                new_service_vals = {
                    'booking_id': target_booking.id,
                    'service_id': service_line.service_id.id,
                    'service_type': service_line.service_type,
                    'amount': service_line.amount,
                    'note': service_line.note,
                    'state': 'draft',
                }
                self.env['hotel.booking.service.line'].create(new_service_vals)
                services_copied += 1
        
        # 2. Transferir órdenes de venta
        sale_orders = self.env['sale.order'].search([('booking_id', '=', self.id)])
        orders_transferred = 0
        if sale_orders:
            sale_orders.write({'booking_id': target_booking.id})
            orders_transferred = len(sale_orders)
        
        _logger.info('Datos copiados: %d servicios, %d órdenes transferidas', services_copied, orders_transferred)
        
        # 3. Mensajes informativos
        self.message_post(
            body=_('✅ Datos transferidos a reserva %s: %d servicios manuales, %d órdenes de venta.') % (
                target_booking.sequence_id or f'#{target_booking.id}', services_copied, orders_transferred
            ),
            subject=_('Transferencia de Datos Completada')
        )
        
        target_booking.message_post(
            body=_('📥 Datos recibidos desde reserva %s: %d servicios manuales, %d órdenes de venta.') % (
                self.sequence_id or f'#{self.id}', services_copied, orders_transferred
            ),
            subject=_('Datos Recibidos')
        )
    
    def action_view_original_booking(self):
        """
        Acción para navegar a la reserva original de la que se originó este cambio de habitación
        """
        if not self.split_from_booking_id:
            raise UserError(_('Esta reserva no tiene una reserva original asociada.'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reserva Original'),
            'res_model': 'hotel.booking',
            'res_id': self.split_from_booking_id.id,
            'view_mode': 'form',
            'target': 'current',
            'context': self.env.context,
        }