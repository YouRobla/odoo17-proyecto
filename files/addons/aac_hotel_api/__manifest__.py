# -*- coding: utf-8 -*-
{
    'name': "aac_hotel_api",

    'summary': "Short (1 phrase/line) summary of the module's purpose",

    'description': """
    Este módulo expone un conjunto completo de endpoints (CRUD) para la gestión de reservas, habitaciones y huéspedes. 
    Está diseñado para alimentar un frontend externo (como React) y permitir la creación de una experiencia de usuario personalizada y dinámica.
    """,

    'author': "Alania Poma Nick",
    'website': "https://consulting-sac.com.pe/",

    'category': 'Uncategorized',
    'version': '17.0',

    'depends': [
        'base',
        'hotel_management_system',
        'hotel_management_system_extension'
        ],

    'data': [
        'security/ir.model.access.csv',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
}

