# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class BookingBillExtension(models.TransientModel):
    _inherit = "booking.bill"
    
    # Campos internos mínimos para funcionalidad (invisibles en vistas)
    additional_services_total = fields.Monetary(
        string="Servicios Adicionales",
        currency_field='currency_id',
        compute='_compute_additional_services_total',
        store=False,
        help='Total interno de servicios adicionales'
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        compute='_compute_currency_id',
        store=False
    )
    
    total_final_amount = fields.Monetary(
        string="Total Final",
        currency_field='currency_id',
        compute='_compute_total_final_amount',
        store=False,
        help='Total final interno'
    )
    
    @api.depends('order_ids')
    def _compute_currency_id(self):
        """Obtener la moneda de las órdenes"""
        for record in self:
            if record.order_ids:
                record.currency_id = record.order_ids[0].currency_id
            else:
                record.currency_id = self.env.company.currency_id
    
    @api.depends('order_ids')
    def _compute_additional_services_total(self):
        """Calcular el total de servicios adicionales (solo para uso interno)"""
        for record in self:
            # Simplificado: solo retorna 0 ya que los servicios ya están en las órdenes
            record.additional_services_total = 0.0
    
    @api.depends('order_ids', 'additional_services_total')
    def _compute_total_final_amount(self):
        """Calcular el total final (simplificado)"""
        for record in self:
            # Solo el total de órdenes ya que los servicios están incluidos
            orders_total = sum(record.order_ids.mapped('amount_total'))
            record.total_final_amount = orders_total
