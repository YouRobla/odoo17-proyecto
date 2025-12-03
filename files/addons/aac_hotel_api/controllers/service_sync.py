from odoo import http
from odoo.http import request
from odoo.exceptions import UserError
from .api_auth import validate_api_key


class ServiceSyncApiController(http.Controller):
    """
    Endpoints relacionados con la sincronización de servicios adicionales
    hacia las órdenes de venta asociadas a una reserva.
    """

    @http.route(
        '/api/hotel/reserva/<int:booking_id>/sync_services',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
        website=False,
    )
    @validate_api_key
    def sync_services_to_sale_orders(self, booking_id):
        """
        Sincronizar los servicios adicionales (early check-in, late check-out,
        servicios manuales, etc.) con las órdenes de venta de la reserva.
        """
        booking = request.env['hotel.booking'].browse(booking_id)

        if not booking.exists():
            raise UserError('La reserva solicitada no existe.')

        # Verificar si se permite la sincronización: solo si hay cambio de habitación o si es una reserva múltiple
        has_room_change = (
            getattr(booking, 'connected_booking_id', False) or 
            getattr(booking, 'split_from_booking_id', False)
        )
        is_multiple_booking = len(booking.booking_line_ids) > 1
        
        # Mantener compatibilidad con is_sync_services_allowed si existe, pero agregar las nuevas condiciones
        sync_allowed = False
        if hasattr(booking, 'is_sync_services_allowed'):
            sync_allowed = booking.is_sync_services_allowed
        
        # El botón aparece solo si hay cambio de habitación o si es una reserva múltiple
        if not (has_room_change or is_multiple_booking) and not sync_allowed:
            raise UserError('La sincronización de servicios solo está disponible para reservas con cambio de habitación o reservas múltiples.')

        bookings_to_process = request.env['hotel.booking']
        bookings_to_process |= booking

        # Incluir reservas conectadas (cambios de habitación) para garantizar que la orden transferida también se sincronice
        if getattr(booking, 'connected_booking_id', False):
            bookings_to_process |= booking.connected_booking_id
        if getattr(booking, 'split_from_booking_id', False):
            bookings_to_process |= booking.split_from_booking_id

        bookings_to_process = bookings_to_process.filtered(lambda b: b.exists())

        total_services_added = 0
        processed_orders = request.env['sale.order']
        booking_results = []

        for target_booking in bookings_to_process:
            services_added = target_booking.update_existing_sale_orders_with_services()
            total_services_added += services_added

            orders = request.env['sale.order'].search([
                ('booking_id', '=', target_booking.id),
                ('state', 'in', ['draft', 'sent', 'sale']),
            ])
            if target_booking.order_id and target_booking.order_id not in orders:
                orders |= target_booking.order_id

            processed_orders |= orders

            booking_results.append({
                'booking_id': target_booking.id,
                'sequence_id': target_booking.sequence_id,
                'services_synced': services_added,
                'order_ids': orders.ids,
            })

        order_payload = [
            {
                'id': order.id,
                'name': order.name,
                'state': order.state,
                'amount_total': order.amount_total,
                'currency_id': order.currency_id.id if order.currency_id else None,
            }
            for order in processed_orders
        ]

        if total_services_added > 0:
            message = f'Se sincronizaron {total_services_added} servicio(s) en la cadena de reservas.'
        else:
            if processed_orders:
                message = 'No se agregaron servicios nuevos; las órdenes ya estaban sincronizadas.'
            else:
                message = 'No se encontraron órdenes de venta para sincronizar.'

        return {
            'success': True,
            'message': message,
            'data': {
                'reserva_id': booking.id,
                'services_synced': total_services_added,
                'orders': order_payload,
                'bookings_processed': booking_results,
            }
        }