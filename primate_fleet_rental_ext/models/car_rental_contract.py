# -*- coding: utf-8 -*-

from odoo import fields, models


class CarRentalContract(models.Model):
	"""Extiende car.rental.contract del módulo de terceros fleet_rental.

	Corrige la resolución del diario de facturación y de la cuenta
	contable usados al facturar el contrato, evitando la dependencia de
	IDs de base de datos fijos del módulo original.
	"""

	_inherit = 'car.rental.contract'

	# FIX [#001]: journal_type y account_type se resolvían por ID de base
	# de datos fijo (id=1 y id=17 respectivamente) en el módulo original.
	# En instancias donde esos IDs no correspondían a un diario de ventas
	# ni a una cuenta de ingresos válidos, la creación de factura fallaba
	# con "Falta el valor requerido para el campo 'Diario' (journal_id)".
	# Se cambia el default para resolverlos por su rol real, filtrado por
	# la compañía activa, y se exponen ambos campos en el formulario para
	# poder corregirlos manualmente por contrato.
	journal_type = fields.Many2one(
		default=lambda self: self._get_default_rental_sale_journal(),
	)
	account_type = fields.Many2one(
		default=lambda self: self._get_default_rental_income_account(),
	)

	# FIX [#002]: el dominio original de vehicle_id exigía
	# rental_check_availability = True además de que el vehículo no
	# estuviera inactivo, lo que ocultaba vehículos válidos del selector.
	# Se quita esa primera condición y se mantiene solo el filtro por
	# estado distinto de 'Inactive'.
	vehicle_id = fields.Many2one(
		domain="[('state_id.name', '!=', 'Inactive')]",
	)

	def _get_default_rental_sale_journal(self):
		"""Busca el diario de ventas por defecto de la compañía activa.

		Returns:
			recordset: account.journal de tipo 'sale' para self.env.company.
				Recordset vacío si no existe ninguno configurado.
		"""
		return self.env['account.journal'].search([
			('type', '=', 'sale'),
			('company_id', '=', self.env.company.id),
		], limit=1)

	def _get_default_rental_income_account(self):
		"""Busca la cuenta de ingresos por defecto de la compañía activa.

		Returns:
			recordset: account.account de tipo 'income' asociada a
				self.env.company. Recordset vacío si no existe ninguna
				configurada.
		"""
		return self.env['account.account'].search([
			('account_type', '=', 'income'),
			('company_ids', 'in', self.env.company.id),
		], limit=1)
