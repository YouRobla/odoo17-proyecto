# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class ChangeRoomWizard(models.TransientModel):
    _name = 'hotel.booking.line.change.room.wizard'
    _description = 'Change Room Wizard'

    booking_id = fields.Many2one('hotel.booking', required=True, readonly=True)
    booking_line_id = fields.Many2one('hotel.booking.line', required=True, readonly=True)
    current_room_id = fields.Many2one('product.product', string='Current Room', readonly=True)
    
    # Fechas flexibles para el cambio
    change_start_date = fields.Date(string='Change Start Date', required=True)
    change_end_date = fields.Date(string='Change End Date', required=True)
    
    # Habitación nueva y precios
    new_room_id = fields.Many2one('product.product', string='New Room', required=True, domain="[('is_room_type','=',True)]")
    use_custom_price = fields.Boolean(string='Use Custom Price', default=False)
    custom_price = fields.Monetary(string='Custom Price Per Night', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='booking_id.currency_id', readonly=True)
    
    # Habitaciones disponibles (computado)
    available_rooms = fields.Many2many('product.product', string='Available Rooms', compute='_compute_available_rooms')
    
    # Información adicional
    note = fields.Text(string='Reason / Notes')
    
    # Campos para mostrar información
    total_nights = fields.Integer(string='Total Nights', compute='_compute_total_nights')
    estimated_total = fields.Monetary(string='Estimated Total', currency_field='currency_id', compute='_compute_estimated_total')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        line = None
        if self.env.context.get('default_booking_line_id'):
            line = self.env['hotel.booking.line'].browse(self.env.context['default_booking_line_id'])
        if line:
            res['booking_line_id'] = line.id
            res['booking_id'] = line.booking_id.id
            res['current_room_id'] = line.product_id.id
            # Proponer fechas de cambio basadas en la reserva actual
            today = fields.Date.today()
            if line.booking_id.check_in and line.booking_id.check_out:
                start = line.booking_id.check_in.date() if hasattr(line.booking_id.check_in, 'date') else line.booking_id.check_in
                end = line.booking_id.check_out.date() if hasattr(line.booking_id.check_out, 'date') else line.booking_id.check_out
                # Proponer desde mañana hasta el final de la reserva
                proposed_start = max(today, start)
                # Permitir modificar la fecha de fin - usar la fecha original como sugerencia
                proposed_end = end
                res['change_start_date'] = proposed_start
                res['change_end_date'] = proposed_end
        return res

    @api.depends('change_start_date', 'change_end_date')
    def _compute_total_nights(self):
        for record in self:
            if record.change_start_date and record.change_end_date:
                record.total_nights = max(0, (record.change_end_date - record.change_start_date).days)
            else:
                record.total_nights = 0

    @api.depends('new_room_id', 'use_custom_price', 'custom_price', 'total_nights')
    def _compute_estimated_total(self):
        for record in self:
            if record.new_room_id and record.total_nights > 0:
                if record.use_custom_price:
                    # Permitir precio personalizado de 0 o cualquier valor
                    custom_price = record.custom_price if record.custom_price is not False else 0.0
                    record.estimated_total = custom_price * record.total_nights
                else:
                    base_price = record.new_room_id.list_price or 0
                    record.estimated_total = base_price * record.total_nights
            else:
                record.estimated_total = 0

    @api.depends('change_start_date', 'change_end_date', 'booking_id')
    def _compute_available_rooms(self):
        for record in self:
            if not record.change_start_date or not record.change_end_date or not record.booking_id:
                record.available_rooms = False
                return
            
            # Buscar habitaciones disponibles en el rango de fechas
            available_room_ids = []
            
            # Obtener todas las habitaciones del hotel
            hotel_rooms = self.env['product.product'].search([
                ('is_room_type', '=', True),
                ('product_tmpl_id.hotel_id', '=', record.booking_id.hotel_id.id)
            ])
            
            for room in hotel_rooms:
                if self._is_room_available(room, record.change_start_date, record.change_end_date):
                    available_room_ids.append(room.id)
            
            record.available_rooms = [(6, 0, available_room_ids)]

    def _validate_inputs(self):
        self.ensure_one()
        booking = self.booking_id
        if not booking.check_in or not booking.check_out:
            raise ValidationError(_('Booking must have a valid check-in and check-out date.'))

        # Validar fechas de cambio
        if not self.change_start_date or not self.change_end_date:
            raise ValidationError(_('Please select both start and end dates for the room change.'))

        if self.change_start_date >= self.change_end_date:
            raise ValidationError(_('Change start date must be before change end date.'))

        start = booking.check_in.date() if hasattr(booking.check_in, 'date') else booking.check_in
        end = booking.check_out.date() if hasattr(booking.check_out, 'date') else booking.check_out
        
        # Validación más flexible: permitir extender la fecha de fin
        if not (start <= self.change_start_date < self.change_end_date):
            raise ValidationError(_('Change start date must be before change end date and within the original booking period.'))
        
        # Permitir extender la fecha de fin más allá de la reserva original
        if self.change_start_date < start:
            raise ValidationError(_('Change start date cannot be before the original booking start date.'))

        if self.new_room_id == self.current_room_id:
            raise ValidationError(_('Please select a different room.'))

        # Validar disponibilidad de la nueva habitación
        if not self._is_room_available(self.new_room_id, self.change_start_date, self.change_end_date):
            raise UserError(_('The selected room is not available for the chosen period.'))

        # Validar precio personalizado si se usa
        if self.use_custom_price and self.custom_price is False:
            raise ValidationError(_('Please enter a custom price. You can enter 0 if you want the room change to be free.'))

    def _is_room_available(self, room, start_date, end_date):
        # Check overlapping booking lines using the same room (simple availability check)
        overlapping_lines = self.env['hotel.booking.line'].search([
            ('product_id', '=', room.id),
            ('booking_id.status_bar', 'not in', ['cancelled', 'no_show']),
            ('booking_id', '!=', self.booking_id.id),
            ('booking_id.check_in', '<', fields.Datetime.to_datetime(end_date)),
            ('booking_id.check_out', '>', fields.Datetime.to_datetime(start_date)),
        ], limit=1)
        return not bool(overlapping_lines)

    def action_confirm(self):
        self.ensure_one()
        self._validate_inputs()
        
        # Validar requisitos para creación de servicios
        self._validate_service_creation_requirements()

        booking = self.booking_id
        line = self.booking_line_id

        # Compute dates - asegurar que todas son date objects
        start = booking.check_in.date() if hasattr(booking.check_in, 'date') else booking.check_in
        end = booking.check_out.date() if hasattr(booking.check_out, 'date') else booking.check_out
        
        # Asegurar que start y end sean objetos date
        if isinstance(start, datetime):
            start = start.date()
        if isinstance(end, datetime):
            end = end.date()
        
        change_start = self.change_start_date
        change_end = self.change_end_date

        # Convertir a date si es necesario (solo si es datetime)
        if isinstance(change_start, datetime):
            change_start = change_start.date()
        if isinstance(change_end, datetime):
            change_end = change_end.date()

        # NUEVA LÓGICA: Crear nueva reserva en lugar de dividir
        # Las fechas ingresadas por el usuario se respetan TAL CUAL (del 12 al 15 = del 12 al 15)
        # NO se ajustan automáticamente para cerrar gaps
        
        # 1. Determinar cómo manejar la reserva original
        # REGLA: Solo modificar la reserva original si el cambio ocurre ANTES o DURANTE la estancia original
        # Si el cambio es DESPUÉS de la reserva original, NO expandir la original
        
        if change_start <= end:
            # El cambio ocurre durante o antes del final de la reserva original
            # Acortar la reserva original para que termine en change_start
            original_end_date = change_start
        else:
            # El cambio ocurre DESPUÉS del final de la reserva original
            # NO modificar la fecha de fin de la reserva original
            original_end_date = end
        
        original_days = (original_end_date - start).days  # Sin +1, ya que original_end_date es el último día
        
        # Verificar si la nueva fecha de fin extiende la reserva original
        extends_booking = change_end > end

        # Obtener parámetros del contexto (sin crear campos nuevos)
        preserve_original_status = self.env.context.get('preserve_original_status', False)
        # Obtener el estado original del booking actual (antes de cualquier cambio)
        original_status = self.env.context.get('original_status') or booking.status_bar or 'initial'
        
        # Verificar consistencia
        total_original_nights = (end - start).days
        original_nights = original_days if original_days > 0 else 0
        change_nights = (change_end - change_start).days
        if original_days > 0:
            # Crear datetime para original_end_date manteniendo la hora original
            new_checkout = fields.Datetime.to_datetime(original_end_date)
            if hasattr(booking.check_out, 'time') and new_checkout:
                new_checkout = new_checkout.replace(
                    hour=booking.check_out.hour, 
                    minute=booking.check_out.minute, 
                    second=booking.check_out.second
                )
            
            # Determinar el estado a usar según preserve_original_status del contexto
            if preserve_original_status:
                # Preservar el estado original
                status_to_use = original_status
            else:
                # Usar lógica por defecto: mantener en checkin para continuar la estancia
                status_to_use = 'checkin'
            
            # Actualizar la reserva original para que termine antes del cambio
            booking.with_context(skip_room_validation=True).write({
                'status_bar': status_to_use,
                'check_out': new_checkout
            })
            # NOTA: No actualizamos booking_days manualmente porque es un campo computado
            # que se recalcula automáticamente basándose en check_in y check_out del booking
        else:
            # Si el cambio es desde el inicio
            if preserve_original_status:
                # Preservar el estado original en lugar de cancelar
                booking.with_context(skip_room_validation=True).write({
                    'status_bar': original_status
                })
                booking.message_post(
                    body=_('Reserva original modificada debido a cambio de habitación desde el inicio. Estado preservado: %s') % original_status,
                    subject=_('Reserva Modificada por Cambio')
                )
            else:
                # Cancelar la reserva original (comportamiento por defecto)
                booking.write({'status_bar': 'cancelled'})
                booking.message_post(
                    body=_('Reserva original cancelada debido a cambio de habitación desde el inicio.'),
                    subject=_('Reserva Cancelada por Cambio')
                )

        # 2. Crear nueva reserva para el período de cambio
        # Calcular precio unitario basado en la configuración del usuario
        if self.use_custom_price:
            price_unit = self.custom_price if self.custom_price is not False else 0.0
        else:
            # Usar precio de la habitación nueva o precio actual de la línea como fallback
            price_unit = self.new_room_id.list_price or line.price or 0.0
        
        # Crear datetimes para la nueva reserva
        # Prioridad: horas del contexto (enviadas desde API) > horas de la reserva original
        new_checkin = fields.Datetime.to_datetime(change_start)
        if not new_checkin:
            raise UserError(_('Error: No se pudo convertir la fecha de inicio a datetime.'))
        
        # Obtener horas del contexto si están disponibles (enviadas desde el API)
        change_start_hour = self.env.context.get('change_start_hour')
        change_start_minute = self.env.context.get('change_start_minute')
        change_end_hour = self.env.context.get('change_end_hour')
        change_end_minute = self.env.context.get('change_end_minute')
        
        # Usar horas del contexto si están disponibles, sino usar horas de la reserva original
        if change_start_hour is not None and change_start_minute is not None:
            # Usar horas enviadas desde el API
            new_checkin = new_checkin.replace(
                hour=change_start_hour,
                minute=change_start_minute,
                second=0
            )
        elif hasattr(booking.check_in, 'time') and isinstance(booking.check_in, datetime):
            # Fallback: usar horas de la reserva original
            new_checkin = new_checkin.replace(
                hour=booking.check_in.hour,
                minute=booking.check_in.minute, 
                second=booking.check_in.second
            )
            
        new_checkout_end = fields.Datetime.to_datetime(change_end)
        if not new_checkout_end:
            raise UserError(_('Error: No se pudo convertir la fecha de fin a datetime.'))
        
        # Usar horas del contexto si están disponibles, sino usar horas de la reserva original
        if change_end_hour is not None and change_end_minute is not None:
            # Usar horas enviadas desde el API
            new_checkout_end = new_checkout_end.replace(
                hour=change_end_hour,
                minute=change_end_minute,
                second=0
            )
        elif hasattr(booking.check_out, 'time') and isinstance(booking.check_out, datetime):
            # Fallback: usar horas de la reserva original
            new_checkout_end = new_checkout_end.replace(
                hour=booking.check_out.hour,
                minute=booking.check_out.minute,
                second=booking.check_out.second
            )
        
        # Determinar el estado para la nueva reserva (usar contexto)
        preserve_original_status = self.env.context.get('preserve_original_status', False)
        original_status = self.env.context.get('original_status') or booking.status_bar or 'initial'
        
        if preserve_original_status:
            # Usar el estado original si se debe preservar
            new_reservation_status = original_status
        else:
            # Usar estado confirmed por defecto
            new_reservation_status = 'confirmed'
        
        # Copiar TODOS los datos de la reserva original
        new_booking_vals = {
            'partner_id': booking.partner_id.id,
            'check_in': new_checkin,
            'check_out': new_checkout_end,
            'hotel_id': booking.hotel_id.id if booking.hotel_id else False,
            'user_id': booking.user_id.id if booking.user_id else self.env.user.id,
            'status_bar': new_reservation_status,  # Usar estado preservado o confirmed
            'company_id': booking.company_id.id,
            'currency_id': booking.currency_id.id,
            'pricelist_id': booking.pricelist_id.id if booking.pricelist_id else False,
            # Copiar información básica
            'booking_reference': booking.booking_reference or 'manual',  # Asegurar valor válido
            'origin': f"{booking.origin or 'Original'} - Cambio habitación",
            'description': f"{booking.description or ''}\n[CAMBIO DE HABITACIÓN desde {line.product_id.name}]".strip(),
            # Vínculo logístico directo con la reserva original
            'split_from_booking_id': booking.id,
            # Copiar motivo de viaje si existe
            'motivo_viaje': booking.motivo_viaje if hasattr(booking, 'motivo_viaje') else 'Cambio de habitación',
            # NO copiar cargos adicionales para evitar duplicación en orden de venta
            # Los servicios (early check-in, late check-out) pertenecen a la reserva original
            'early_checkin_charge': 0,
            'late_checkout_charge': 0,
            'early_checkin_product_id': False,
            'late_checkout_product_id': False,
            # Copiar información de agente si existe
            'agent_id': booking.agent_id.id if hasattr(booking, 'agent_id') and booking.agent_id else False,
            'commission_type': booking.commission_type if hasattr(booking, 'commission_type') and booking.commission_type else False,
            'agent_commission_amount': booking.agent_commission_amount if hasattr(booking, 'agent_commission_amount') else 0,
            'agent_commission_percentage': booking.agent_commission_percentage if hasattr(booking, 'agent_commission_percentage') else 0,
        }
        
        # Crear la nueva reserva
        try:
            new_booking = self.env['hotel.booking'].create(new_booking_vals)
        except Exception as e:
            raise UserError(_('Error creando nueva reserva: %s') % str(e))
        
        # 3. Crear línea de reserva para la nueva habitación
        # IMPORTANTE: Sistema maneja NOCHES (ej: 1-4 enero = 3 noches)
        change_days = (change_end - change_start).days  # Número de NOCHES
        if change_days <= 0:
            change_days = 1  # Mínimo 1 noche
            
            
        new_line_vals = {
            'booking_id': new_booking.id,
                'product_id': self.new_room_id.id,
            'booking_days': change_days,
                'price': price_unit,
                'discount': line.discount,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
            }
        
        new_line = self.env['hotel.booking.line'].create(new_line_vals)
        
        # Establecer precio original
        if hasattr(new_line, 'original_price'):
            new_line.original_price = self.new_room_id.product_tmpl_id.list_price or self.new_room_id.list_price or price_unit
        
        # Ahora cambiar el estado a checkin (después de crear la línea)
        new_booking.write({'status_bar': 'checkin'})
        
        # Marcar las reservas como conectadas para la línea de transición
        
        # Actualizar reserva original como origen del cambio
        booking.with_context(skip_room_validation=True).write({
            'connected_booking_id': new_booking.id,
            'is_room_change_origin': True
        })
        # Actualizar nueva reserva como destino del cambio
        new_booking.write({
            'connected_booking_id': booking.id,
            'is_room_change_destination': True
        })
        
        # Nota: No es necesario invalidate_recordset() aquí. Odoo manejará automáticamente
        # el flush de los cambios al final de la transacción. Las llamadas a invalidate_recordset()
        # pueden causar errores de serialización en PostgreSQL cuando hay transacciones concurrentes.

        # 4. Copiar información de huéspedes a la nueva reserva
        if hasattr(line, 'guest_info_ids') and line.guest_info_ids:
            for guest in line.guest_info_ids:
                guest_vals = {
                    'booking_line_id': new_line.id,
                    'name': guest.name,
                    'age': guest.age,
                    'gender': guest.gender,
                    'partner_id': guest.partner_id.id if guest.partner_id else False,
                }
                # Usar el modelo correcto para huéspedes (guest.info del módulo hotel_management_system)
                try:
                    self.env['guest.info'].create(guest_vals)
                except Exception:
                    # Si no existe el modelo, omitir la copia de huéspedes
                    # Esto puede ocurrir si el módulo hotel_management_system no está instalado
                    pass

        # 5. TRANSFERIR SERVICIOS MANUALES de la reserva original a la nueva
        # ESTRATEGIA: Mover (no copiar) los servicios manuales para evitar duplicación
        manual_services = self.env['hotel.booking.service.line'].search([
            ('booking_id', '=', booking.id),
            ('service_id.name', '=', 'Servicio Manual')
        ])
        
        services_transferred = 0
        if manual_services:
            for service in manual_services:
                # MOVER el servicio a la nueva reserva (no crear copia)
                service.write({'booking_id': new_booking.id})
                services_transferred += 1

        # 6. GESTIÓN DE FACTURACIÓN - ESTRATEGIA UNIFICADA  
        # IMPORTANTE: Copiar servicios ANTES de transferir órdenes de venta
        # porque las órdenes pueden contener referencias a los servicios
        
        sale_orders = self.env['sale.order'].search([('booking_id', '=', booking.id)])
        if sale_orders:
            # ESTRATEGIA: Transferir toda la facturación a la nueva reserva
            # Esto mantiene la facturación unificada y evita confusiones
            # IMPORTANTE: Las órdenes transferidas YA CONTIENEN los servicios adicionales
            # (early check-in, late check-out, servicios manuales) por lo que NO se deben
            # agregar nuevamente para evitar duplicación
            sale_orders.write({'booking_id': new_booking.id})

            first_order = sale_orders[:1]
            if first_order:
                new_booking.order_id = first_order.id
                booking.order_id = False
            
            # Actualizar el mensaje
            booking.message_post(
                body=_('✅ Facturación transferida a nueva reserva: %s. Toda la facturación se centralizará en la nueva reserva.') % ', '.join(sale_orders.mapped('name')),
                subject=_('Transferencia de Facturación')
            )
            new_booking.message_post(
                body=_('💰 Facturación completa recibida desde reserva original: %s. Esta reserva contiene toda la información de facturación.') % ', '.join(sale_orders.mapped('name')),
                subject=_('Facturación Centralizada')
            )
        else:
            # Si no hay órdenes de venta, crear una nueva para la nueva reserva
            new_booking.message_post(
                body=_('📄 Nueva reserva sin órdenes de venta previas. La facturación se generará automáticamente.'),
                subject=_('Nueva Facturación')
            )

        # 7. CREAR LÍNEAS DE PRODUCTO PARA LA NUEVA RESERVA
        # Crear línea de producto para la habitación
        room_product = self.new_room_id
        if room_product:
            # Buscar si ya existe una línea para esta habitación en las órdenes transferidas
            existing_line = None
            if sale_orders:
                for order in sale_orders:
                    existing_line = order.order_line.filtered(lambda l: l.product_id == room_product)
                    if existing_line:
                        break
            
            if not existing_line:
                # Crear nueva línea de producto para la habitación
                if sale_orders:
                    # Usar la primera orden transferida
                    order = sale_orders[0]
                else:
                    # Crear nueva orden de venta
                    order = self.env['sale.order'].create({
                        'partner_id': new_booking.partner_id.id,
                        'booking_id': new_booking.id,
                        'date_order': fields.Datetime.now(),
                        'company_id': new_booking.company_id.id,
                        'currency_id': new_booking.currency_id.id,
                        'pricelist_id': new_booking.pricelist_id.id,
                    })
                
                # Crear línea de producto para la habitación
                order_line = self.env['sale.order.line'].create({
                    'order_id': order.id,
                    'product_id': room_product.id,
                    'name': f'Habitación {self.new_room_id.name} - {change_days} noche(s)',
                    'product_uom_qty': change_days,
                    'price_unit': price_unit,
                    'product_uom': room_product.uom_id.id,
                })
        
        # 8. NOTA: NO AGREGAR SERVICIOS ADICIONALES PARA EVITAR DUPLICACIÓN
        # Los servicios (early check-in, late check-out, servicios manuales) pertenecen 
        # a la reserva original y ya están facturados en sus órdenes de venta.
        # Solo se factura la nueva habitación en el cambio.

        # OPCIÓN B: No crear reserva de continuación
        # Las noches entre la original y el cambio se pierden intencionalmente

        # Mensajes en el chatter de todas las reservas
        original_msg = _('Cambio de habitación aplicado. Reserva original modificada para terminar el %s (estado: CHECK-IN).') % change_start.strftime('%d/%m/%Y')
        if original_days > 0:
            original_msg += _(' Permanece %d noche(s) en %s.') % (original_days, self.current_room_id.display_name)
        
        # Agregar información si se extendió la reserva
        if extends_booking:
            extension_days = (change_end - end).days
            original_msg += _(' La nueva reserva extiende la estancia %d día(s) adicional(es).') % extension_days

        booking.message_post(
            body=original_msg + _(' Nueva reserva creada: <a href="#" data-oe-model="hotel.booking" data-oe-id="%s">%s</a>') % (new_booking.id, new_booking.sequence_id or f'Booking-{new_booking.id}'),
            subject=_('Cambio de Habitación - Reserva Original')
        )
        
        new_booking.message_post(
            body=_('Nueva reserva creada por cambio de habitación desde reserva original: <a href="#" data-oe-model="hotel.booking" data-oe-id="%s">%s</a>. Período: %s a %s (%d noche(s)) en %s.') % (
                booking.id, booking.sequence_id or f'Booking-{booking.id}',
                change_start.strftime('%d/%m/%Y'), change_end.strftime('%d/%m/%Y'),
                change_days, self.new_room_id.display_name
            ),
            subject=_('Nueva Reserva por Cambio de Habitación')
        )
        

        # Mostrar mensaje de éxito al usuario
        message = _('Cambio de habitación completado exitosamente.\n\n')
        if original_days > 0:
            message += _('• Reserva original: %d noche(s) en %s (hasta %s) - Estado: CHECK-IN\n') % (
                original_days, 
                self.current_room_id.display_name, 
                original_end_date.strftime('%d/%m/%Y')
            )
        
        # Mostrar información de extensión si aplica
        if extends_booking:
            extension_days = (change_end - end).days
            message += _('• Nueva reserva: %d noche(s) en %s (del %s al %s) - Estado: CHECK-IN\n') % (
                change_days, 
                self.new_room_id.display_name, 
                change_start.strftime('%d/%m/%Y'), 
                change_end.strftime('%d/%m/%Y')
            )
            message += _('• ⭐ EXTENSIÓN: La reserva se extendió %d día(s) adicional(es) más allá de la fecha original\n') % extension_days
        else:
            message += _('• Nueva reserva: %d noche(s) en %s (del %s al %s) - Estado: CHECK-IN\n') % (
                change_days, 
                self.new_room_id.display_name, 
                change_start.strftime('%d/%m/%Y'), 
                change_end.strftime('%d/%m/%Y')
            )
        
        # Contar servicios finales en la nueva reserva
        final_manual_services = self.env['hotel.booking.service.line'].search_count([
            ('booking_id', '=', new_booking.id),
            ('service_id.name', '=', 'Servicio Manual')
        ])
        
        # Notificación más breve
        brief_message = _('Cambio de habitación completado: %s → %s\n📋 Servicios manuales transferidos: %s') % (
            self.current_room_id.name, 
            self.new_room_id.name,
            services_transferred if 'services_transferred' in locals() else final_manual_services
        )
        
        # Agregar información de extensión si aplica
        if extends_booking:
            extension_days = (change_end - end).days
            brief_message += _('\n⭐ EXTENSIÓN: +%d día(s) adicional(es)') % extension_days
        
        # Mostrar notificación usando el método estándar de Odoo
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cambio Exitoso'),
                'message': brief_message + '\n🔗 Reservas conectadas para visualización en Gantt',
                'type': 'success',
                'sticky': True,  # Hacer sticky para verificar el mensaje
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload'  # Forzar recarga completa para actualizar Gantt
                }
            }
        }
    
    def _create_service_line(self, booking, sale_orders, service_or_product, name, amount):
        """
        Método auxiliar robusto para crear líneas de servicio en las órdenes de venta
        Maneja tanto objetos hotel.service como product.product
        """
        if not service_or_product:
            return None
        
        # Determinar si es un hotel.service o product.product
        actual_product = self._get_product_from_service_or_product(service_or_product, name)
        
        if not actual_product:
            return None
        
        # Usar la primera orden disponible o crear una nueva
        if sale_orders:
            order = sale_orders[0]
        else:
            order = self.env['sale.order'].create({
                'partner_id': booking.partner_id.id,
                'booking_id': booking.id,
                'date_order': fields.Datetime.now(),
                'company_id': booking.company_id.id,
                'currency_id': booking.currency_id.id,
                'pricelist_id': booking.pricelist_id.id,
            })
        
        # Obtener UOM por defecto de forma robusta
        default_uom = self._get_default_uom(actual_product)
        
        # Crear línea de servicio con manejo robusto de errores
        try:
            order_line = self.env['sale.order.line'].create({
                'order_id': order.id,
                'product_id': actual_product.id,
                'name': name,
                'product_uom_qty': 1,
                'price_unit': amount,
                'product_uom': default_uom.id,
            })
            
            return order_line
            
        except Exception:
            return None
    
    def _get_product_from_service_or_product(self, service_or_product, service_name):
        """
        Obtiene el product.product correcto desde hotel.service o product.product
        """
        
        # Si ya es un product.product, devolverlo directamente
        if hasattr(service_or_product, 'uom_id') and service_or_product._name == 'product.product':
            return service_or_product
        
        # Si es un hotel.service, buscar o crear el product.product correspondiente
        if service_or_product._name == 'hotel.service':
            # Buscar producto existente por nombre
            existing_product = self.env['product.product'].search([
                ('name', '=', service_name),
                ('type', '=', 'service')
            ], limit=1)
            
            if existing_product:
                return existing_product
            
            # Crear nuevo producto si no existe
            try:
                new_product = self.env['product.product'].create({
                    'name': service_name,
                    'type': 'service',
                    'list_price': 0.0,  # El precio se establece en la línea
                    'sale_ok': True,
                    'purchase_ok': False,
                })
                return new_product
                
            except Exception:
                return None
        
        # Fallback: intentar obtener cualquier producto de servicio genérico
        generic_service = self.env['product.product'].search([
            ('type', '=', 'service'),
            ('sale_ok', '=', True)
        ], limit=1)
        
        if generic_service:
            return generic_service
        
        return None
    
    def _get_default_uom(self, product):
        """
        Obtiene la UOM por defecto de forma robusta
        """
        
        # Intentar obtener UOM del producto
        if hasattr(product, 'uom_id') and product.uom_id:
            return product.uom_id
        
        # Fallback: UOM por defecto de la compañía o sistema
        default_uom = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
        if default_uom:
            return default_uom
        
        # Último fallback: buscar cualquier UOM de unidades
        fallback_uom = self.env['uom.uom'].search([
            ('category_id.name', 'ilike', 'unit')
        ], limit=1)
        
        if fallback_uom:
            return fallback_uom
        
        # Si no hay nada disponible, crear UOM básica
        try:
            unit_category = self.env['uom.category'].search([('name', '=', 'Unit')], limit=1)
            if not unit_category:
                unit_category = self.env['uom.category'].create({'name': 'Unit'})
            
            emergency_uom = self.env['uom.uom'].create({
                'name': 'Unit',
                'category_id': unit_category.id,
                'factor': 1.0,
                'uom_type': 'reference',
            })
            return emergency_uom
            
        except Exception:
            raise UserError(_('Error crítico: No se pudo configurar la unidad de medida para el servicio. Contacte al administrador.'))
    
    def _validate_service_creation_requirements(self):
        """
        Validar que todos los requisitos estén disponibles para crear servicios
        """
        
        validation_errors = []
        
        # Verificar que existe al menos una UOM en el sistema
        uom_count = self.env['uom.uom'].search_count([])
        if uom_count == 0:
            validation_errors.append(_('No hay unidades de medida configuradas en el sistema.'))
        
        # Verificar que se pueden crear productos
        try:
            test_product = self.env['product.product'].search([('type', '=', 'service')], limit=1)
        except Exception as e:
            validation_errors.append(_('Error accediendo a productos: %s') % str(e))
        
        if validation_errors:
            error_msg = _('Errores de validación para cambio de habitación:\n%s') % '\n'.join(validation_errors)
            raise ValidationError(error_msg)
        
        return True 