# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.tests import TransactionCase


class RentalCase(TransactionCase):
    """Shared setup: the eight bikes, the two pricelists and a customer."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Booking = cls.env["primate.booking"]
        cls.Block = cls.env["primate.booking.block"]
        cls.params = cls.env["motosrack.rental.parameters"]

        cls.general = cls.env.ref("motosrack_rental.pricelist_general")
        cls.moradores = cls.env.ref("motosrack_rental.pricelist_moradores")
        cls.rental_product = cls.env.ref(
            "motosrack_rental.product_rental_moto"
        ).product_variant_id
        cls.helmet_product = cls.env.ref(
            "motosrack_rental.product_helmet"
        ).product_variant_id
        cls.journal_pix = cls.env.ref("motosrack_rental.journal_pix")
        cls.journal_cash = cls.env.ref("motosrack_rental.journal_cash")

        cls.moto1 = cls.env.ref("motosrack_rental.moto_1")
        cls.moto2 = cls.env.ref("motosrack_rental.moto_2")

        cls.customer = cls.env["res.partner"].create(
            {"name": "João Turista", "phone": "+55 84 99999-0001"}
        )
        cls.resident = cls.env["res.partner"].create(
            {
                "name": "Maria Moradora",
                "phone": "+55 84 99999-0002",
                "property_product_pricelist": cls.moradores.id,
            }
        )

        # A fixed week, far from "now", so nothing depends on the clock.
        cls.day0 = datetime(2030, 6, 10, 10, 0, 0)

    @classmethod
    def _at(cls, days=0, hours=0):
        return cls.day0 + timedelta(days=days, hours=hours)

    def _new_booking(self, days=1, vehicle=None, partner=None, start=None, **extra):
        """Create a draft booking the way the quick-create form does."""
        start = start or self._at()
        values = {
            "vehicle_id": (vehicle or self.moto1).id,
            "partner_id": (partner or self.customer).id,
            "start": start,
            "stop": start + timedelta(days=days),
        }
        values.update(extra)
        return self.Booking.create(values)

    def _stock_qty(self, location):
        """On-hand helmets in ``location``."""
        return sum(
            self.env["stock.quant"]
            .search(
                [
                    ("product_id", "=", self.helmet_product.id),
                    ("location_id", "=", location.id),
                ]
            )
            .mapped("quantity")
        )

    def _receive_helmets(self, quantity):
        """Put helmets in stock so the moves have something to take."""
        stock = self.env.ref("stock.stock_location_stock")
        self.env["stock.quant"].with_context(inventory_mode=True).create(
            {
                "product_id": self.helmet_product.id,
                "location_id": stock.id,
                "inventory_quantity": quantity,
            }
        ).action_apply_inventory()
