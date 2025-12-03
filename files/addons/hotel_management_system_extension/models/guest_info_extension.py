# -*- coding: utf-8 -*-
"""
Extensión del modelo guest.info para añadir funcionalidad de contactos
"""

from odoo import fields, models, api

import logging
_logger = logging.getLogger(__name__)


class GuestInfoExtension(models.Model):
    """Extensión del modelo Guest Information para añadir relación con contactos"""
    
    _inherit = "guest.info"
    
    # Añadir el campo partner_id
    partner_id = fields.Many2one(
        "res.partner", 
        string="Contacto", 
        help="Contacto asociado al huésped"
    )
    
    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """
        Sincronizar el nombre cuando se selecciona un contacto
        """
        if self.partner_id:
            self.name = self.partner_id.name
            # Los campos gender y age no existen en res.partner por defecto
            # Solo sincronizamos el nombre

    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribimos el método 'create' para asegurar que el nombre
        se llene desde el contacto antes de guardar en la base de datos.
        """
        for vals in vals_list:
            # Verificamos si se está enviando un 'partner_id' y si el 'name' no viene
            if vals.get('partner_id') and not vals.get('name'):
                # Buscamos el nombre del contacto y lo añadimos a los valores de creación
                partner_name = self.env['res.partner'].browse(vals['partner_id']).name
                vals['name'] = partner_name
                
        # Llamamos al método 'create' original, pero ahora con el 'name' ya incluido
        return super(GuestInfoExtension, self).create(vals_list)