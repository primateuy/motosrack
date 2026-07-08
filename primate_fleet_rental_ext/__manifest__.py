# -*- coding: utf-8 -*-
{
	'name': 'Primate Fleet Rental Extension',
	'version': '19.0.1.0.0',
	'author': 'PrimateUY',
	'website': 'https://primate.uy',
	'category': 'Fleet',
	'license': 'AGPL-3',
	'summary': """
		Correcciones y extensiones propias de Primate sobre el módulo de terceros fleet_rental.
		""",
	'description': """
		Módulo de extensión que aísla correcciones de Primate sobre el módulo
		de terceros fleet_rental (Cybrosys), sin modificar su código original.

		Incluye:
		- Resolución correcta del diario de facturación (journal_type) y de
		  la cuenta contable (account_type) en car.rental.contract,
		  reemplazando los IDs de base de datos hardcodeados (1 y 17) del
		  módulo original por búsquedas por rol real (diario de tipo venta,
		  cuenta de ingresos), filtradas por la compañía activa.
		- Exposición de ambos campos en el formulario del contrato para que
		  puedan ajustarse manualmente por contrato si hace falta.
		""",
	'depends': ['fleet_rental', 'account'],
	'data': [
		# VISTAS
		'views/car_rental_contract_views.xml',
	],
	'auto_install': False,
	'installable': True,
	'application': False,
}
