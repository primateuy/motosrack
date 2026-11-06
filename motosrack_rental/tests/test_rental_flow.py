# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRentalFlow(TransactionCase):
    """Cubre el ciclo completo de alquiler y el control de disponibilidad."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Cliente de prueba'})
        cls.brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Honda'})
        cls.moto_model = cls.env['fleet.vehicle.model'].create({
            'name': 'CB 500',
            'brand_id': cls.brand.id,
            'vehicle_type': 'bike',
        })
        cls.vehicle = cls.env['fleet.vehicle'].create({
            'model_id': cls.moto_model.id,
            'license_plate': 'AAA-1111',
        })
        cls.vehicle_2 = cls.env['fleet.vehicle'].create({
            'model_id': cls.moto_model.id,
            'license_plate': 'BBB-2222',
        })
        cls.rental_product = cls.env['product.product'].create({
            'name': 'Alquiler CB 500 por dia',
            'type': 'service',
            'is_rental': True,
            'fleet_model_id': cls.moto_model.id,
            'list_price': 150.0,
            'invoice_policy': 'order',
        })
        cls.start = datetime(2026, 11, 10, 9, 0, 0)
        cls.end = datetime(2026, 11, 13, 9, 0, 0)

    def _make_order(self, vehicle=None, start=None, end=None):
        """Crea un pedido de alquiler listo para confirmar."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'rental_start': start or self.start,
            'rental_end': end or self.end,
            'order_line': [(0, 0, {
                'product_id': self.rental_product.id,
                'vehicle_id': (vehicle or self.vehicle).id,
                'product_uom_qty': 3,
            })],
        })
        return order

    # -------------------------------------------------------------- flujo

    def test_ciclo_completo(self):
        """Reserva, entrega y devolucion dejan los estados y el odometro bien."""
        order = self._make_order()
        self.assertTrue(order.is_rental)
        self.assertEqual(order.rental_days, 3)
        self.assertEqual(order.rental_status, 'no')

        order.action_confirm()
        self.assertEqual(order.rental_status, 'reserved')
        self.assertEqual(self.vehicle.rental_status, 'available',
                         'Reservada todavia no es estar afuera')

        order.order_line.pickup_odometer = 1000
        order.action_rental_pickup()
        self.assertEqual(order.rental_status, 'picked_up')
        self.assertTrue(order.actual_pickup_date)
        self.assertEqual(self.vehicle.rental_status, 'rented')
        self.assertEqual(self.vehicle.current_rental_order_id, order)
        self.assertEqual(self.vehicle.odometer, 1000)

        order.order_line.return_odometer = 1250
        order.action_rental_return()
        self.assertEqual(order.rental_status, 'returned')
        self.assertTrue(order.actual_return_date)
        self.assertEqual(order.order_line.km_driven, 250)
        self.assertEqual(self.vehicle.rental_status, 'available')
        self.assertEqual(self.vehicle.odometer, 1250)

    def test_dias_redondean_hacia_arriba(self):
        """Toda fraccion de dia se cobra como dia completo."""
        order = self._make_order(
            start=datetime(2026, 11, 10, 9, 0, 0),
            end=datetime(2026, 11, 11, 15, 0, 0),
        )
        self.assertEqual(order.rental_days, 2)

    def test_cantidad_sigue_a_las_fechas(self):
        """Cambiar el periodo reajusta los dias facturables de las lineas."""
        order = self._make_order()
        self.assertEqual(order.order_line.product_uom_qty, 3)
        order.rental_end = datetime(2026, 11, 15, 9, 0, 0)
        self.assertEqual(order.rental_days, 5)
        self.assertEqual(order.order_line.product_uom_qty, 5)

    # ------------------------------------------------------ disponibilidad

    def test_doble_reserva_bloqueada(self):
        """La misma moto no puede comprometerse dos veces en el mismo periodo."""
        self._make_order().action_confirm()
        solapado = self._make_order(
            start=datetime(2026, 11, 12, 9, 0, 0),
            end=datetime(2026, 11, 14, 9, 0, 0),
        )
        with self.assertRaises(UserError):
            solapado.action_confirm()

    def test_periodos_sin_solape_conviven(self):
        """Dos alquileres consecutivos de la misma moto son validos."""
        self._make_order().action_confirm()
        posterior = self._make_order(
            start=datetime(2026, 11, 20, 9, 0, 0),
            end=datetime(2026, 11, 22, 9, 0, 0),
        )
        posterior.action_confirm()
        self.assertEqual(posterior.rental_status, 'reserved')

    def test_otra_moto_mismo_periodo(self):
        """El bloqueo es por moto, no por modelo."""
        self._make_order().action_confirm()
        otra = self._make_order(vehicle=self.vehicle_2)
        otra.action_confirm()
        self.assertEqual(otra.rental_status, 'reserved')

    def test_cancelar_libera_la_moto(self):
        """Un pedido cancelado deja de bloquear el periodo."""
        order = self._make_order()
        order.action_confirm()
        order.action_cancel()
        self.assertEqual(order.rental_status, 'no')
        nuevo = self._make_order()
        nuevo.action_confirm()
        self.assertEqual(nuevo.rental_status, 'reserved')

    def test_entregada_sin_devolver_bloquea(self):
        """Una moto que sigue afuera no puede entregarse a otro cliente hoy."""
        order = self._make_order(
            start=datetime(2026, 11, 1, 9, 0, 0),
            end=datetime(2026, 11, 3, 9, 0, 0),
        )
        order.action_confirm()
        order.action_rental_pickup()
        ahora = datetime.now()
        choque = self._make_order(
            start=ahora - timedelta(hours=1),
            end=ahora + timedelta(days=2),
        )
        with self.assertRaises(UserError):
            choque.action_confirm()

    # ------------------------------------------------------- validaciones

    def test_confirmar_sin_moto_falla(self):
        """No se confirma un alquiler con una linea sin moto asignada."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'rental_start': self.start,
            'rental_end': self.end,
            'order_line': [(0, 0, {
                'product_id': self.rental_product.id,
                'product_uom_qty': 3,
            })],
        })
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_confirmar_sin_fechas_falla(self):
        """No se confirma un alquiler sin periodo definido."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'order_line': [(0, 0, {
                'product_id': self.rental_product.id,
                'vehicle_id': self.vehicle.id,
                'product_uom_qty': 3,
            })],
        })
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_moto_repetida_en_el_pedido(self):
        """Cada linea del pedido debe llevar una moto distinta."""
        order = self.env['sale.order'].create({
            'partner_id': self.partner.id,
            'rental_start': self.start,
            'rental_end': self.end,
            'order_line': [
                (0, 0, {'product_id': self.rental_product.id,
                        'vehicle_id': self.vehicle.id, 'product_uom_qty': 3}),
                (0, 0, {'product_id': self.rental_product.id,
                        'vehicle_id': self.vehicle.id, 'product_uom_qty': 3}),
            ],
        })
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_devolucion_invertida_falla(self):
        """La devolucion prevista tiene que ser posterior a la salida."""
        with self.assertRaises(ValidationError):
            self._make_order(
                start=datetime(2026, 11, 13, 9, 0, 0),
                end=datetime(2026, 11, 10, 9, 0, 0),
            )

    def test_odometro_de_llegada_menor_falla(self):
        """El odometro no puede retroceder entre salida y llegada."""
        order = self._make_order()
        order.action_confirm()
        order.order_line.pickup_odometer = 1000
        with self.assertRaises(ValidationError):
            order.order_line.return_odometer = 900

    def test_tarifa_debe_ser_servicio(self):
        """Una tarifa de alquiler marcada sobre un bien fisico se rechaza."""
        with self.assertRaises(ValidationError):
            self.env['product.product'].create({
                'name': 'Tarifa mal tipada',
                'type': 'consu',
                'is_rental': True,
            })

    # --------------------------------------------------- devolucion tardia

    def test_devolucion_tardia_reajusta_los_dias(self):
        """Si el cliente se pasa de fecha, se facturan los dias reales."""
        order = self._make_order()
        order.action_confirm()
        order.action_rental_pickup()
        # Simula una salida de hace 6 dias para que la devolucion de hoy
        # supere los 3 dias contratados.
        order.actual_pickup_date = datetime.now() - timedelta(days=6)
        order.action_rental_return()
        self.assertEqual(order.order_line.product_uom_qty, 6,
                         'Se deben facturar los dias realmente usados')

    def test_devolucion_tardia_con_factura_no_toca_cantidades(self):
        """Con factura emitida, la diferencia se avisa pero no se reescribe."""
        order = self._make_order()
        order.action_confirm()
        order.action_rental_pickup()
        order._create_invoices()
        order.actual_pickup_date = datetime.now() - timedelta(days=6)
        order.action_rental_return()
        self.assertEqual(order.order_line.product_uom_qty, 3,
                         'No se altera un pedido ya facturado')
