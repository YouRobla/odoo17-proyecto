# -*- coding: utf-8 -*-
"""
Extensión del modelo res.partner para agregar campos faltantes
"""
from odoo import models, fields, api, _


class ResPartnerExtension(models.Model):
    _inherit = 'res.partner'

    # Campo para evitar errores cuando el módulo calendar no está instalado
    meeting_count = fields.Integer(
        string="# Meetings",
        compute='_compute_meeting_count',
        help='Número de reuniones programadas'
    )

    @api.depends()
    def _compute_meeting_count(self):
        """
        Computar el número de reuniones
        Si el módulo calendar está instalado, usar la lógica real
        Si no, retornar 0
        """
        for partner in self:
            try:
                # Intentar usar la lógica del módulo calendar si está disponible
                if hasattr(self.env['calendar.event'], 'search'):
                    meetings = self.env['calendar.event'].search([
                        ('partner_ids', 'in', partner.id)
                    ])
                    partner.meeting_count = len(meetings)
                else:
                    partner.meeting_count = 0
            except Exception:
                # Si hay algún error, simplemente retornar 0
                partner.meeting_count = 0 