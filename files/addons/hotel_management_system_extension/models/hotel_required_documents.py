# -*- coding: utf-8 -*-
from odoo import models, _

class CustomerDocumentExtension(models.TransientModel):
    _inherit = 'customer.document'
    
    def confirm_doc(self):
        """Sobrescribir para realizar check-in sin validar documentos"""
        # Obtener la reserva activa
        active_booking_id = self.env["hotel.booking"].browse(
            self._context.get("active_ids")
        )
        
        # Verificar si la reserva está en estado 'confirmed' para hacer check-in
        if active_booking_id.status_bar == 'confirmed':
            # Ya no guardamos documentos ni validamos
            
            # Usar el método action_check_in que tiene la validación de fechas
            active_booking_id.action_check_in()
            
            # Actualizar estado de habitaciones si existe el campo
            for line in active_booking_id.booking_line_ids:
                if hasattr(line.product_id, 'room_status'):
                    line.product_id.room_status = 'occupied'
            
            # Crear mensaje de seguimiento
            active_booking_id.message_post(
                body=_('Check-in realizado exitosamente. El huésped está ahora en la habitación.'),
                subject=_('Check-in Completado')
            )
            
            # Enviar email si está configurado (opcional)
            template_id = self.env.ref(
                "hotel_management_system.hotel_booking_allot_id", raise_if_not_found=False
            )
            if template_id:
                allot_config = self.env["ir.config_parameter"].sudo().get_param(
                    "hotel_management_system.send_on_allot"
                )
                if allot_config:
                    template_id.send_mail(active_booking_id.id, force_send=True)
        else:
            # Si no está en estado confirmed, usar el comportamiento original
            return super().confirm_doc()