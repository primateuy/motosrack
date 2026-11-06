# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    """Cada linea de alquiler reserva una moto concreta por el periodo del pedido."""

    _inherit = 'sale.order.line'

    is_rental = fields.Boolean(
        string='Es alquiler',
        related='product_id.is_rental',
        store=True,
        index=True,
    )
    fleet_model_id = fields.Many2one(
        comodel_name='fleet.vehicle.model',
        string='Modelo de moto',
        related='product_id.fleet_model_id',
    )
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Moto',
        ondelete='restrict',
        copy=False,
        index='btree_not_null',
        help='Moto concreta que se entrega en esta linea.',
    )
    pickup_odometer = fields.Float(
        string='Odometro salida',
        copy=False,
    )
    return_odometer = fields.Float(
        string='Odometro llegada',
        copy=False,
    )
    km_driven = fields.Float(
        string='Km recorridos',
        compute='_compute_km_driven',
        store=True,
        aggregator='sum',
    )

    @api.depends('pickup_odometer', 'return_odometer')
    def _compute_km_driven(self):
        for line in self:
            if line.pickup_odometer and line.return_odometer:
                line.km_driven = line.return_odometer - line.pickup_odometer
            else:
                line.km_driven = 0.0

    @api.constrains('vehicle_id', 'is_rental')
    def _check_vehicle_only_on_rental(self):
        """Una moto solo tiene sentido en una linea de tarifa de alquiler."""
        for line in self:
            if line.vehicle_id and not line.is_rental:
                raise ValidationError(_(
                    'La linea "%s" no es una tarifa de alquiler, no puede '
                    'llevar una moto asignada.', line.product_id.display_name,
                ))

    @api.constrains('vehicle_id', 'return_odometer', 'pickup_odometer')
    def _check_odometer_order(self):
        """El odometro de llegada nunca puede ser menor que el de salida."""
        for line in self:
            if not line.pickup_odometer or not line.return_odometer:
                continue
            if line.return_odometer < line.pickup_odometer:
                raise ValidationError(_(
                    'En la moto %s el odometro de llegada no puede ser menor '
                    'que el de salida.', line.vehicle_id.display_name,
                ))

    @api.onchange('product_id')
    def _onchange_product_id_rental(self):
        """Limpia la moto si el producto deja de ser una tarifa de alquiler."""
        if not self.product_id.is_rental:
            self.vehicle_id = False
        elif self.vehicle_id and self.fleet_model_id:
            if self.vehicle_id.model_id != self.fleet_model_id:
                self.vehicle_id = False

    @api.onchange('vehicle_id')
    def _onchange_vehicle_id(self):
        """Avisa en el acto si la moto elegida ya esta comprometida."""
        if not self.vehicle_id or not self.order_id.rental_start:
            return
        conflictos = self.vehicle_id._get_rental_conflicts(
            self.order_id.rental_start,
            self.order_id.rental_end,
            ignore_lines=self.order_id.order_line,
        )
        if conflictos:
            return {
                'warning': {
                    'title': _('Moto no disponible'),
                    'message': _(
                        '%(moto)s ya esta comprometida en %(pedido)s durante '
                        'ese periodo.',
                        moto=self.vehicle_id.display_name,
                        pedido=conflictos[0].order_id.display_name,
                    ),
                }
            }

    @api.onchange('is_rental')
    def _onchange_is_rental_qty(self):
        """La cantidad de una linea de alquiler son los dias del pedido."""
        if self.is_rental and self.order_id.rental_days:
            self.product_uom_qty = self.order_id.rental_days
