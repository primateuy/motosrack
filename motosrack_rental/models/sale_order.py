# -*- coding: utf-8 -*-

import logging
import math

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

RENTAL_STATUS = [
    ('no', 'Sin alquiler'),
    ('reserved', 'Reservado'),
    ('picked_up', 'Entregado'),
    ('returned', 'Devuelto'),
]


class SaleOrder(models.Model):
    """Convierte el pedido de venta en el contrato de alquiler.

    El periodo de alquiler es unico por pedido: todas las motos del pedido
    salen y vuelven juntas. Es lo habitual en una rentadora y evita la
    combinatoria de fechas por linea.
    """

    _inherit = 'sale.order'

    is_rental = fields.Boolean(
        string='Es alquiler',
        compute='_compute_is_rental',
        store=True,
    )
    rental_start = fields.Datetime(
        string='Salida prevista',
        copy=False,
        tracking=True,
    )
    rental_end = fields.Datetime(
        string='Devolucion prevista',
        copy=False,
        tracking=True,
    )
    rental_days = fields.Integer(
        string='Dias',
        compute='_compute_rental_days',
        store=True,
        help='Dias facturables del alquiler. Toda fraccion de dia se cobra '
             'como dia completo, con un minimo de un dia.',
    )
    rental_status = fields.Selection(
        selection=RENTAL_STATUS,
        string='Estado del alquiler',
        default='no',
        copy=False,
        index=True,
        tracking=True,
        required=True,
    )
    actual_pickup_date = fields.Datetime(
        string='Salida real',
        copy=False,
        readonly=True,
    )
    actual_return_date = fields.Datetime(
        string='Devolucion real',
        copy=False,
        readonly=True,
    )
    rental_vehicle_count = fields.Integer(
        string='Motos',
        compute='_compute_rental_vehicle_count',
    )

    # -------------------------------------------------------------------
    # COMPUTES
    # -------------------------------------------------------------------

    @api.depends('order_line.is_rental')
    def _compute_is_rental(self):
        for order in self:
            order.is_rental = any(order.order_line.mapped('is_rental'))

    @api.depends('rental_start', 'rental_end')
    def _compute_rental_days(self):
        for order in self:
            order.rental_days = self._rental_days_between(
                order.rental_start, order.rental_end
            )

    @api.depends('order_line.vehicle_id')
    def _compute_rental_vehicle_count(self):
        for order in self:
            order.rental_vehicle_count = len(order.order_line.vehicle_id)

    @api.model
    def _rental_days_between(self, start, end):
        """Dias facturables entre dos momentos, redondeando hacia arriba.

        Args:
            start (datetime): inicio del alquiler.
            end (datetime): fin del alquiler.

        Returns:
            int: cantidad de dias a cobrar. 0 si falta alguna fecha o el
                periodo es invalido.
        """
        if not start or not end or end <= start:
            return 0
        days = math.ceil((end - start).total_seconds() / 86400.0)
        return max(1, int(days))

    # -------------------------------------------------------------------
    # RESTRICCIONES
    # -------------------------------------------------------------------

    @api.constrains('rental_start', 'rental_end', 'is_rental')
    def _check_rental_period(self):
        for order in self:
            if not order.is_rental:
                continue
            if order.rental_start and order.rental_end:
                if order.rental_end <= order.rental_start:
                    raise ValidationError(_(
                        'En el pedido %s la devolucion prevista debe ser '
                        'posterior a la salida.', order.display_name,
                    ))

    # -------------------------------------------------------------------
    # SINCRONIZACION DE CANTIDADES
    # -------------------------------------------------------------------

    def _sync_rental_quantities(self, days=None):
        """Pone la cantidad de las lineas de alquiler en dias de alquiler.

        Args:
            days (int): dias a aplicar. Si es None usa rental_days del pedido.
        """
        for order in self:
            qty = order.rental_days if days is None else days
            if not qty:
                continue
            rental_lines = order.order_line.filtered('is_rental')
            rental_lines.filtered(
                lambda line: line.product_uom_qty != qty
            ).product_uom_qty = qty

    @api.onchange('rental_start', 'rental_end')
    def _onchange_rental_dates(self):
        """Refleja en el acto el cambio de fechas sobre las lineas."""
        if self.rental_days:
            for line in self.order_line.filtered('is_rental'):
                line.product_uom_qty = self.rental_days

    def write(self, vals):
        """Mantiene las cantidades alineadas si cambian las fechas."""
        res = super().write(vals)
        if {'rental_start', 'rental_end'} & set(vals):
            self.filtered(
                lambda order: order.is_rental and order.state in ('draft', 'sent')
            )._sync_rental_quantities()
        return res

    # -------------------------------------------------------------------
    # VALIDACIONES DE ALQUILER
    # -------------------------------------------------------------------

    def _check_rental_ready(self):
        """Valida fechas, asignacion de motos y disponibilidad del periodo."""
        for order in self:
            if not order.is_rental:
                continue

            if not order.rental_start or not order.rental_end:
                raise UserError(_(
                    'Indica la salida y la devolucion prevista antes de '
                    'confirmar el alquiler %s.', order.display_name,
                ))

            rental_lines = order.order_line.filtered('is_rental')
            sin_moto = rental_lines.filtered(lambda line: not line.vehicle_id)
            if sin_moto:
                raise UserError(_(
                    'Falta asignar la moto en estas lineas de %(order)s:\n%(lines)s',
                    order=order.display_name,
                    lines='\n'.join('- %s' % line.product_id.display_name
                                    for line in sin_moto),
                ))

            vehicles = rental_lines.vehicle_id
            if len(vehicles) != len(rental_lines):
                raise UserError(_(
                    'La misma moto esta repetida en varias lineas del pedido '
                    '%s. Cada linea debe llevar una moto distinta.',
                    order.display_name,
                ))

            order._check_rental_availability()

    def _check_rental_availability(self):
        """Impide reservar una moto que ya esta comprometida en el periodo."""
        self.ensure_one()
        problemas = []
        for line in self.order_line.filtered('is_rental'):
            conflictos = line.vehicle_id._get_rental_conflicts(
                self.rental_start, self.rental_end,
                ignore_lines=self.order_line,
            )
            for conflicto in conflictos:
                problemas.append(_(
                    '- %(moto)s ya esta comprometida en %(pedido)s '
                    '(%(desde)s a %(hasta)s)',
                    moto=line.vehicle_id.display_name,
                    pedido=conflicto.order_id.display_name,
                    desde=conflicto.order_id.rental_start,
                    hasta=conflicto.order_id.rental_end,
                ))
        if problemas:
            raise UserError(_(
                'No se puede confirmar el alquiler, hay motos no disponibles '
                'en ese periodo:\n%s', '\n'.join(problemas),
            ))

    # -------------------------------------------------------------------
    # FLUJO
    # -------------------------------------------------------------------

    def action_confirm(self):
        """Confirma el pedido y deja el alquiler reservado."""
        self._check_rental_ready()
        res = super().action_confirm()
        self.filtered(
            lambda order: order.is_rental and order.rental_status == 'no'
        ).rental_status = 'reserved'
        return res

    def action_cancel(self):
        """Al cancelar, libera las motos que el pedido tenia comprometidas."""
        res = super().action_cancel()
        self.filtered(
            lambda order: order.rental_status in ('reserved', 'picked_up')
        ).rental_status = 'no'
        return res

    def action_rental_pickup(self):
        """Registra la entrega de las motos al cliente."""
        for order in self:
            if order.rental_status != 'reserved':
                raise UserError(_(
                    'Solo se pueden entregar las motos de un alquiler '
                    'reservado. El pedido %s esta en estado "%s".',
                    order.display_name,
                    dict(RENTAL_STATUS).get(order.rental_status),
                ))
            order._log_rental_odometer('pickup')
            order.write({
                'actual_pickup_date': fields.Datetime.now(),
                'rental_status': 'picked_up',
            })
            order.message_post(body=_(
                'Motos entregadas al cliente: %s',
                ', '.join(order.order_line.vehicle_id.mapped('display_name')),
            ))
        return True

    def action_rental_return(self):
        """Registra la devolucion y ajusta la facturacion a los dias reales."""
        for order in self:
            if order.rental_status != 'picked_up':
                raise UserError(_(
                    'Solo se puede registrar la devolucion de un alquiler '
                    'entregado. El pedido %s esta en estado "%s".',
                    order.display_name,
                    dict(RENTAL_STATUS).get(order.rental_status),
                ))
            order._log_rental_odometer('return')
            order.write({
                'actual_return_date': fields.Datetime.now(),
                'rental_status': 'returned',
            })
            order._update_quantities_from_actual()
            order.message_post(body=_(
                'Motos devueltas: %s',
                ', '.join(order.order_line.vehicle_id.mapped('display_name')),
            ))
        return True

    def _log_rental_odometer(self, moment):
        """Vuelca los odometros de las lineas al historial de la flota.

        Args:
            moment (str): 'pickup' para la salida, 'return' para la llegada.
        """
        self.ensure_one()
        campo = 'pickup_odometer' if moment == 'pickup' else 'return_odometer'
        Odometer = self.env['fleet.vehicle.odometer']
        vehiculos = self.env['fleet.vehicle'].browse()
        for line in self.order_line.filtered('is_rental'):
            valor = line[campo]
            if not valor or not line.vehicle_id:
                continue
            if valor < line.vehicle_id.odometer:
                raise UserError(_(
                    'El odometro de %(moto)s (%(nuevo)s) no puede ser menor '
                    'que el ultimo registrado (%(actual)s).',
                    moto=line.vehicle_id.display_name,
                    nuevo=valor,
                    actual=line.vehicle_id.odometer,
                ))
            Odometer.create({
                'vehicle_id': line.vehicle_id.id,
                'value': valor,
                'date': fields.Date.context_today(self),
                'driver_id': self.partner_id.id,
            })
            vehiculos |= line.vehicle_id
        # fleet.vehicle.odometer se calcula sin @api.depends, asi que el valor
        # queda cacheado y no refleja los registros recien creados dentro de la
        # misma transaccion. Hay que invalidarlo a mano.
        if vehiculos:
            vehiculos.invalidate_recordset(['odometer'])

    def _update_quantities_from_actual(self):
        """Ajusta los dias facturables al uso real si el cliente se excedio.

        Solo toca el pedido si todavia no se emitio factura, para no dejar
        una linea desalineada con un documento ya contabilizado.
        """
        self.ensure_one()
        if not self.actual_pickup_date or not self.actual_return_date:
            return
        dias_reales = self._rental_days_between(
            self.actual_pickup_date, self.actual_return_date
        )
        if dias_reales <= self.rental_days:
            return
        if self.invoice_ids.filtered(lambda move: move.state != 'cancel'):
            self.message_post(body=_(
                'El alquiler duro %(reales)s dias en lugar de %(previstos)s, '
                'pero el pedido ya tiene factura: ajusta la diferencia a mano.',
                reales=dias_reales, previstos=self.rental_days,
            ))
            return
        self._sync_rental_quantities(days=dias_reales)
        self.message_post(body=_(
            'Devolucion fuera de plazo: se facturan %(reales)s dias en lugar '
            'de los %(previstos)s previstos.',
            reales=dias_reales, previstos=self.rental_days,
        ))
