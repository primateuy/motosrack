# -*- coding: utf-8 -*-
{
    'name': 'MotosRack - Alquiler de motos',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Alquiler de motos con tarifa diaria sobre pedidos de venta y flota',
    'author': 'PrimateUY',
    'website': 'https://primate.uy',
    'license': 'AGPL-3',
    'description': """
MotosRack - Alquiler de motos
=============================

Implementa el alquiler de motos sobre el flujo nativo de Odoo
(presupuesto -> pedido -> factura), sin modulos de terceros.

- Producto de alquiler con tarifa diaria, asociado a un modelo de la flota.
- Cada linea de alquiler reserva una moto concreta por un periodo.
- Control de disponibilidad: una moto no puede reservarse dos veces para
  periodos que se solapan.
- Entrega y devolucion con registro de odometro, que alimenta el historial
  de la flota.
- Al devolver, la cantidad facturable se ajusta a los dias reales de uso.
""",
    'depends': [
        'sale_management',
        'fleet',
    ],
    'data': [
        'data/motosrack_rental_data.xml',
        'views/product_template_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/sale_order_views.xml',
        'views/motosrack_rental_menus.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
}
