# -*- coding: utf-8 -*-
import base64
import json

from odoo import http, fields
from odoo.http import request, Response
from odoo.exceptions import UserError
from odoo.tools import json_default
from .api_auth import validate_api_key


class AdvancePaymentApiController(http.Controller):
    """
    Endpoints auxiliares para soportar el modal de pagos adelantados en el frontend.
    """

    def _parse_json_body(self):
        raw = request.httprequest.data
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf-8'))
        except json.JSONDecodeError as exc:
            raise UserError(f'Formato JSON inválido: {exc}')

    def _prepare_response(self, data, status=200):
        """Preparar respuesta HTTP con formato JSON"""
        return Response(
            json.dumps(data, default=json_default),
            status=status,
            content_type='application/json'
        )

    @http.route(
        '/api/hotel/reserva/<int:booking_id>/advance_payment/options',
        type='http',
        auth='public',
        methods=['GET'],
        csrf=False,
        website=False
    )
    @validate_api_key
    def get_advance_payment_options(self, booking_id):
        """
        Retorna los valores predeterminados y las opciones disponibles para el modal
        de registro de pago (advance payment) basado en la reserva indicada.
        """
        booking = request.env['hotel.booking'].browse(booking_id)
        if not booking.exists():
            return self._prepare_response({
                'success': False,
                'error': 'La reserva solicitada no existe.'
            }, status=404)

        sale_order = booking.order_id
        if not sale_order:
            return self._prepare_response({
                'success': False,
                'error': 'La reserva no tiene una orden de venta asociada.'
            }, status=400)

        company = sale_order.company_id or request.env.company

        amount = max(sale_order.amount_total - sale_order.paid_amount, 0.0)

        journal_domain = [
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', company.id),
        ]
        journals = request.env['account.journal'].search(journal_domain)
        journal_options = [
            {
                'value': journal.id,
                'label': journal.display_name,
                'code': journal.code,
                'type': journal.type,
            }
            for journal in journals
        ]

        payment_type = 'inbound'
        default_journal = journals[:1]
        if default_journal:
            if payment_type == 'inbound':
                available_method_lines = default_journal.inbound_payment_method_line_ids
            else:
                available_method_lines = default_journal.outbound_payment_method_line_ids
        else:
            available_method_lines = request.env['account.payment.method.line']

        payment_method_options = [
            {
                'value': line.id,
                'label': line.name,
                'code': line.payment_method_id.code,
                'method_type': line.payment_method_id.payment_type,
            }
            for line in available_method_lines
        ]

        payment_type_field_info = request.env['account.payment'].fields_get(['payment_type']).get('payment_type', {})
        selection = payment_type_field_info.get('selection', [])
        payment_type_options = [
            {'value': value, 'label': label}
            for value, label in selection
        ]

        response_payload = {
            'success': True,
            'data': {
                'defaults': {
                    'amount': amount,
                    'payment_type': payment_type,
                    'payment_date': fields.Date.context_today(request.env.user),
                    'journal_id': default_journal.id if default_journal else None,
                    'journal_name': default_journal.display_name if default_journal else None,
                    'payment_method_line_id': available_method_lines[:1].id if available_method_lines else None,
                    'payment_method_line_name': available_method_lines[:1].name if available_method_lines else None,
                    'currency': {
                        'id': sale_order.currency_id.id,
                        'name': sale_order.currency_id.name,
                        'symbol': sale_order.currency_id.symbol,
                    },
                    'partner': {
                        'id': sale_order.partner_id.id,
                        'name': sale_order.partner_id.display_name,
                    },
                    'company': {
                        'id': company.id,
                        'name': company.name,
                    },
                    'sale_order_id': sale_order.id,
                    'sale_order_name': sale_order.name,
                },
                'payment_type_options': payment_type_options,
                'journal_options': journal_options,
                'payment_method_options': payment_method_options,
            }
        }

        return self._prepare_response(response_payload)

    @http.route(
        '/api/hotel/reserva/<int:booking_id>/print_bill',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
        website=False
    )
    @validate_api_key
    def print_reservation_bill(self, booking_id):
        """
        Generar el PDF de la factura de hospedaje (combine/separate/detailed).

        Body JSON opcional:
        {
            "print_mode": "combine" | "separate",   # default combine
            "detailed": false                       # true -> detailed report
        }
        """
        booking = request.env['hotel.booking'].browse(booking_id)
        if not booking.exists():
            raise UserError('La reserva solicitada no existe.')

        data = self._parse_json_body()
        print_mode = data.get('print_mode', 'combine')
        detailed = bool(data.get('detailed', False))

        if print_mode not in ('combine', 'separate'):
            raise UserError('print_mode debe ser "combine" o "separate".')

        ctx = {
            'active_model': 'hotel.booking',
            'active_id': booking.id,
            'active_ids': [booking.id],
        }

        wizard_vals = {'print_bill': print_mode}
        wizard = request.env['booking.bill'].with_context(ctx).create(wizard_vals)

        try:
            if detailed:
                action = wizard.print_detailed_report()
            else:
                action = wizard.print_report()
        except Exception as exc:
            raise UserError(f'Error al generar el reporte: {exc}')

        report_name = action.get('report_name') or action.get('report_file')
        if not report_name:
            raise UserError('No se pudo determinar el reporte a imprimir.')

        action_data = action.get('data') or {}
        docids = action_data.get('ids') or wizard.ids
        pdf_bytes, _ = request.env['ir.actions.report']._render_qweb_pdf(
            report_name, res_ids=docids, data=action_data
        )
        filename = action.get('display_name') or f'{booking.sequence_id or "booking"}_bill.pdf'
        if not filename.lower().endswith('.pdf'):
            filename = f'{filename}.pdf'

        return {
            'success': True,
            'data': {
                'filename': filename,
                'mimetype': 'application/pdf',
                'content': base64.b64encode(pdf_bytes).decode('utf-8'),
            }
        }

    @http.route(
        '/api/hotel/reserva/<int:booking_id>/create_invoice',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
        website=False
    )
    def create_reservation_invoice(self, booking_id):
        """
        Crear la factura asociada a la reserva (equivalente al botón Create Invoice).
        """
        booking = request.env['hotel.booking'].browse(booking_id)
        if not booking.exists():
            raise UserError('La reserva solicitada no existe.')

        if not booking.order_id:
            raise UserError('La reserva no tiene una orden de venta asociada.')

        allowed_statuses = {'checkout', 'cleaning_needed'}
        if booking.status_bar not in allowed_statuses:
            raise UserError('Solo se puede crear la factura cuando la reserva está en estado "checkout" o "cleaning_needed".')

        existing_invoice_ids = set(booking.invoice_ids.ids)
        booking.create_invoice()
        booking.invalidate_recordset(['invoice_ids'])

        new_invoices = booking.invoice_ids.filtered(lambda inv: inv.id not in existing_invoice_ids)
        if not new_invoices:
            new_invoices = booking.invoice_ids

        invoice_payload = [
            {
                'id': invoice.id,
                'name': invoice.name,
                'move_type': invoice.move_type,
                'state': invoice.state,
                'amount_total': invoice.amount_total,
                'currency_id': invoice.currency_id.id,
            }
            for invoice in new_invoices
        ]

        return {
            'success': True,
            'message': 'Factura creada correctamente.',
            'data': {
                'reserva_id': booking.id,
                'invoices': invoice_payload,
            }
        }

    @http.route(
        '/api/hotel/reserva/<int:booking_id>/mark_room_ready',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False,
        website=False
    )
    def mark_room_ready(self, booking_id):
        """
        Ejecutar el flujo de 'Habitación Lista' (action_mark_room_ready).
        """
        booking = request.env['hotel.booking'].browse(booking_id)
        if not booking.exists():
            raise UserError('La reserva solicitada no existe.')

        if booking.status_bar != 'cleaning_needed':
            raise UserError('La habitación solo puede marcarse como lista desde el estado "cleaning_needed".')

        booking.action_mark_room_ready()
        booking.invalidate_recordset(['status_bar'])

        return {
            'success': True,
            'message': 'La reserva fue marcada como "Habitación Lista".',
            'data': {
                'reserva_id': booking.id,
                'status_bar': booking.status_bar,
            }
        }


