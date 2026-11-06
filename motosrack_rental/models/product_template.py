# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    """Agrega al producto la nocion de tarifa de alquiler de moto."""

    _inherit = 'product.template'

    is_rental = fields.Boolean(
        string='Tarifa de alquiler',
        index=True,
        help='Marca el producto como una tarifa de alquiler de moto. En las '
             'lineas del pedido la cantidad representa dias de alquiler y hay '
             'que asignar una moto concreta de la flota.',
    )
    fleet_model_id = fields.Many2one(
        comodel_name='fleet.vehicle.model',
        string='Modelo de moto',
        ondelete='restrict',
        index='btree_not_null',
        help='Modelo de la flota que se entrega con esta tarifa. Limita que '
             'motos pueden asignarse a la linea de alquiler. Si se deja vacio, '
             'se puede asignar cualquier moto habilitada para alquiler.',
    )

    @api.constrains('is_rental', 'type')
    def _check_rental_product_type(self):
        """La tarifa de alquiler no es un bien fisico: debe ser servicio."""
        for template in self:
            if template.is_rental and template.type != 'service':
                raise ValidationError(_(
                    'La tarifa de alquiler "%s" debe ser un producto de tipo '
                    'Servicio.', template.display_name,
                ))

    @api.onchange('is_rental')
    def _onchange_is_rental(self):
        """Al marcar la tarifa, deja el producto listo para alquilar."""
        if self.is_rental:
            self.type = 'service'
            self.invoice_policy = 'order'
