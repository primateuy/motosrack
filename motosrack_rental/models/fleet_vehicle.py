# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class FleetVehicle(models.Model):
    """Agrega a la moto de la flota su disponibilidad para alquiler."""

    _inherit = 'fleet.vehicle'

    rental_ok = fields.Boolean(
        string='Disponible para alquiler',
        default=True,
        index=True,
        help='Si se desmarca, la moto deja de ofrecerse en el selector de las '
             'lineas de alquiler (por ejemplo, mientras esta en taller).',
    )
    rental_line_ids = fields.One2many(
        comodel_name='sale.order.line',
        inverse_name='vehicle_id',
        string='Lineas de alquiler',
    )
    rental_count = fields.Integer(
        string='Alquileres',
        compute='_compute_rental_count',
    )
    rental_status = fields.Selection(
        selection=[
            ('available', 'Disponible'),
            ('rented', 'Alquilada'),
            ('unavailable', 'No disponible'),
        ],
        string='Estado de alquiler',
        compute='_compute_rental_status',
        store=True,
        index=True,
    )
    current_rental_order_id = fields.Many2one(
        comodel_name='sale.order',
        string='Alquiler en curso',
        compute='_compute_rental_status',
        store=True,
    )

    @api.depends('rental_ok', 'active', 'rental_line_ids.order_id.rental_status')
    def _compute_rental_status(self):
        """La moto esta alquilada mientras haya un pedido entregado sin devolver."""
        for vehicle in self:
            out_lines = vehicle.rental_line_ids.filtered(
                lambda line: line.order_id.rental_status == 'picked_up'
            )
            if out_lines:
                vehicle.rental_status = 'rented'
                vehicle.current_rental_order_id = out_lines[0].order_id
            else:
                vehicle.current_rental_order_id = False
                vehicle.rental_status = (
                    'available' if vehicle.rental_ok else 'unavailable'
                )

    def _compute_rental_count(self):
        """Cuenta los pedidos de alquiler confirmados de cada moto."""
        grouped = self.env['sale.order.line']._read_group(
            domain=[
                ('vehicle_id', 'in', self.ids),
                ('order_id.rental_status', '!=', 'no'),
            ],
            groupby=['vehicle_id'],
            aggregates=['__count'],
        )
        counts = {vehicle.id: count for vehicle, count in grouped}
        for vehicle in self:
            vehicle.rental_count = counts.get(vehicle.id, 0)

    def _get_rental_conflicts(self, start, end, ignore_lines=None):
        """Devuelve las lineas de alquiler que chocan con el periodo pedido.

        Una moto entregada y todavia no devuelta bloquea hasta ahora mismo
        aunque su fecha prevista de devolucion ya haya pasado: fisicamente
        sigue afuera. Una reserva bloquea exactamente su periodo previsto.

        Args:
            start (datetime): inicio del periodo a verificar.
            end (datetime): fin del periodo a verificar.
            ignore_lines (recordset): lineas a excluir de la verificacion,
                tipicamente las del propio pedido que se esta confirmando.

        Returns:
            recordset: sale.order.line en conflicto. Vacio si esta libre.
        """
        self.ensure_one()
        SaleOrderLine = self.env['sale.order.line']
        if not start or not end:
            return SaleOrderLine.browse()

        domain = [
            ('vehicle_id', '=', self.id),
            ('order_id.rental_status', 'in', ('reserved', 'picked_up')),
        ]
        if ignore_lines:
            domain.append(('id', 'not in', ignore_lines.ids))

        now = fields.Datetime.now()
        conflicts = SaleOrderLine.browse()
        for line in SaleOrderLine.search(domain):
            order = line.order_id
            busy_start = order.actual_pickup_date or order.rental_start
            busy_end = order.rental_end
            if order.rental_status == 'picked_up' and busy_end and busy_end < now:
                # Sigue afuera: bloquea hasta que se registre la devolucion.
                busy_end = now
            if not busy_start or not busy_end:
                continue
            if busy_start < end and busy_end > start:
                conflicts |= line
        return conflicts

    def action_view_rentals(self):
        """Abre los pedidos de alquiler de la moto."""
        self.ensure_one()
        orders = self.rental_line_ids.order_id.filtered(
            lambda order: order.rental_status != 'no'
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Alquileres de %s', self.display_name),
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('id', 'in', orders.ids)],
            'context': {'create': False},
        }
