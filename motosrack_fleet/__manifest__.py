# -*- coding: utf-8 -*-
{
    'name': 'MotosRack - Flota y mantenimiento',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Fleet',
    'summary': 'Planes de mantenimiento por km y tiempo, y documentacion de la flota',
    'author': 'PrimateUY',
    'website': 'https://primate.uy',
    'license': 'AGPL-3',
    'description': """
MotosRack - Flota y mantenimiento
=================================

- Planes de mantenimiento preventivo por kilometraje y por tiempo,
  asignados por modelo de moto.
- Calculo del proximo service de cada moto y alerta cuando esta por
  vencer o ya vencio.
- Documentacion de cada moto (CRLV, seguro, IPVA) con fecha de
  vencimiento y aviso anticipado.
- Tarea programada diaria que crea actividades para el responsable de
  flota sobre services y documentos vencidos o por vencer.
""",
    'depends': [
        'fleet',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/motosrack_fleet_data.xml',
        'data/ir_cron.xml',
        'views/maintenance_plan_views.xml',
        'views/vehicle_document_views.xml',
        'views/fleet_vehicle_views.xml',
        'views/motosrack_fleet_menus.xml',
    ],
    'application': False,
    'installable': True,
    'auto_install': False,
}
