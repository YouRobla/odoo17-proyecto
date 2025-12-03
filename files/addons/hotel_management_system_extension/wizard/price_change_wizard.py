# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class PriceChangeWizard(models.TransientModel):
    _name = 'hotel.booking.line.price.change.wizard'
    _description = 'Wizard para capturar motivo del cambio de precio'

    booking_line_id = fields.Many2one(
        'hotel.booking.line',
        string='Línea de Reserva',
        required=True
    )
    
    original_price = fields.Monetary(
        string='Precio Original',
        currency_field='currency_id',
        readonly=True,
        help='Precio original calculado considerando listas de precios y contexto'
    )
    
    new_price = fields.Monetary(
        string='Nuevo Precio',
        currency_field='currency_id',
        required=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='booking_line_id.booking_id.currency_id',
        readonly=True
    )
    
    reason = fields.Text(
        string='Motivo del Cambio',
        required=True,
        help='Explique el motivo del cambio de precio'
    )
    
    
    @api.model
    def default_get(self, fields_list):
        """Pre-llenar datos del wizard con cálculo robusto del precio original"""
        res = super().default_get(fields_list)
        
        # Obtener ID de la línea de reserva desde diferentes contextos posibles
        booking_line_id = (
            self.env.context.get('default_booking_line_id') or 
            self.env.context.get('booking_line_id') or
            self.env.context.get('active_id')
        )
        
        if booking_line_id:
            booking_line = self.env['hotel.booking.line'].browse(booking_line_id)
            
            if booking_line.exists():
                # Calcular precio original de forma robusta
                original_price = self._calculate_robust_original_price(booking_line)
                
                res.update({
                    'booking_line_id': booking_line_id,
                    'original_price': original_price,
                    'new_price': booking_line.price or 0.0,
                    'currency_id': booking_line.booking_id.currency_id.id,
                })
                
                _logger.info(
                    'Price Change Wizard initialized for booking line %s: '
                    'original_price=%s',
                    booking_line_id, original_price
                )
        
        return res
    
    def _calculate_robust_original_price(self, booking_line):
        """
        Calcular el precio original de forma robusta considerando diferentes escenarios
        """
        try:
            # 1. Si ya tiene original_price establecido y es mayor a 0, usarlo
            if booking_line.original_price and booking_line.original_price > 0:
                return booking_line.original_price
            
            # 2. Intentar calcular usando lista de precios si está disponible
            if booking_line.booking_id and booking_line.booking_id.pricelist_id:
                pricelist_price = self._get_pricelist_price(booking_line)
                if pricelist_price and pricelist_price > 0:
                    return pricelist_price
            
            # 3. Usar precio de lista del template del producto
            if booking_line.product_id and booking_line.product_id.product_tmpl_id:
                list_price = booking_line.product_id.product_tmpl_id.list_price or 0
                if list_price > 0:
                    return list_price
            
            # 4. Fallback al precio del producto
            if booking_line.product_id:
                product_price = booking_line.product_id.list_price or 0
                if product_price > 0:
                    return product_price
            
            # 5. Si hay un precio actual, usarlo como fallback
            if booking_line.price and booking_line.price > 0:
                return booking_line.price
            
            # 6. Último recurso: 0
            _logger.warning(
                'No se pudo determinar precio original para booking line %s. '
                'Product: %s, Booking: %s',
                booking_line.id, 
                booking_line.product_id.name if booking_line.product_id else 'None',
                booking_line.booking_id.id if booking_line.booking_id else 'None'
            )
            return 0.0
            
        except Exception as e:
            _logger.error(
                'Error calculando precio original para booking line %s: %s',
                booking_line.id, str(e)
            )
            return 0.0
    
    def _get_pricelist_price(self, booking_line):
        """
        Obtener precio desde la lista de precios
        """
        try:
            if not booking_line.booking_id or not booking_line.booking_id.pricelist_id:
                return 0.0
            
            if not booking_line.product_id:
                return 0.0
            
            # Usar el método estándar de Odoo para obtener precio de lista
            pricelist = booking_line.booking_id.pricelist_id
            partner = booking_line.booking_id.partner_id
            
            # Crear contexto para cálculo de precios
            context = {
                'pricelist': pricelist.id,
                'partner': partner.id if partner else False,
                'date': booking_line.booking_id.check_in or fields.Date.today(),
            }
            
            # Obtener precio usando el método estándar
            price = pricelist.get_product_price(
                booking_line.product_id,
                1,  # quantity
                partner=partner,
                date=context.get('date'),
                uom_id=booking_line.product_id.uom_id.id
            )
            
            return price if price else 0.0
            
        except Exception as e:
            _logger.error(
                'Error obteniendo precio de lista para booking line %s: %s',
                booking_line.id, str(e)
            )
            return 0.0
    
    @api.onchange('booking_line_id')
    def _onchange_booking_line_id(self):
        """Recalcular precio original cuando cambia la línea de reserva"""
        if self.booking_line_id:
            original_price = self._calculate_robust_original_price(self.booking_line_id)
            self.original_price = original_price
            self.new_price = self.booking_line_id.price or 0.0
    
    def action_confirm_price_change(self):
        """Confirmar el cambio de precio y actualizar la reserva principal"""
        self.ensure_one()
        
        if not self.booking_line_id:
            raise UserError(_('No se encontró la línea de reserva.'))
        
        # Validar que el nuevo precio sea válido
        if self.new_price < 0:
            raise UserError(_('El nuevo precio no puede ser negativo.'))
        
        # Actualizar el precio original si no estaba establecido
        update_values = {
            'price': self.new_price,
            'discount_reason': self.reason,
        }
        
        # Si no tenía precio original o era 0, establecerlo ahora
        if not self.booking_line_id.original_price or self.booking_line_id.original_price == 0:
            update_values['original_price'] = self.original_price
        
        # Actualizar la línea de reserva
        self.booking_line_id.write(update_values)
        
        # Recalcular descuentos si es necesario
        if self.original_price > 0 and self.new_price != self.original_price:
            if self.new_price < self.original_price:
                discount_amount = self.original_price - self.new_price
                self.booking_line_id.write({'discount_amount': discount_amount})
            else:
                self.booking_line_id.write({'discount_amount': 0.0})
        
        # Actualizar el motivo en la reserva principal
        booking = self.booking_line_id.booking_id
        if booking:
            # Crear un mensaje de seguimiento
            booking.message_post(
                body=_(
                    '<b>Cambio de Precio en Habitación %s:</b><br/>'
                    'Precio Original: %s %s<br/>'
                    'Nuevo Precio: %s %s<br/>'
                    '<b>Motivo:</b> %s'
                ) % (
                    self.booking_line_id.product_id.name,
                    self.original_price,
                    self.currency_id.symbol,
                    self.new_price,
                    self.currency_id.symbol,
                    self.reason
                ),
                subject=_('Cambio de Precio - Habitación %s') % self.booking_line_id.product_id.name
            )
            
            # Actualizar el campo discount_reason de la reserva principal si está vacío
            if not booking.discount_reason:
                booking.discount_reason = _('Cambio de precio en habitación %s: %s') % (
                    self.booking_line_id.product_id.name,
                    self.reason
                )
            
            # Forzar recálculo del precio original de la reserva principal
            if hasattr(booking, 'force_compute_original_price'):
                booking.force_compute_original_price()
        
        _logger.info(
            'Price change confirmed for booking line %s: %s -> %s (reason: %s)',
            self.booking_line_id.id, self.original_price, self.new_price, self.reason
        )
        
        return {'type': 'ir.actions.act_window_close'}
