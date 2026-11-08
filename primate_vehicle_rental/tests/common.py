# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.tests import TransactionCase


# The tiers the business was specified with. They live here, and not in a
# data file, so that the module can be tested without the fleet, the
# pricelists or the journals of any particular shop.
GENERAL_TIERS = [(1, 130.0), (4, 120.0), (7, 100.0), (10, 90.0),
                 (14, 80.0), (21, 70.0), (30, 50.0)]
RESIDENT_TIERS = [(1, 80.0), (4, 75.0), (7, 70.0), (14, 60.0), (30, 40.0)]


class RentalCase(TransactionCase):
    """Shared setup: two vehicles, two tier pricelists, journals, customers."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Booking = cls.env["primate.booking"]
        cls.Block = cls.env["primate.booking.block"]
        cls.params = cls.env["primate.rental.parameters"]

        cls.rental_product = cls.env.ref(
            "primate_vehicle_rental.product_vehicle_rental"
        ).product_variant_id
        cls.helmet_product = cls.env.ref(
            "primate_vehicle_rental.product_helmet"
        ).product_variant_id

        cls.general = cls._build_pricelist("General", GENERAL_TIERS, sequence=1)
        cls.moradores = cls._build_pricelist("Residents", RESIDENT_TIERS, sequence=2)
        cls.env["ir.config_parameter"].sudo().set_param(
            "primate_vehicle_rental.default_pricelist_id", str(cls.general.id)
        )

        cls.journal_pix = cls._build_journal("Transfer", "TTST", "bank")
        cls.journal_cash = cls._build_journal("Cash", "CTST", "cash")

        cls.moto1 = cls._build_vehicle("Test 1")
        cls.moto2 = cls._build_vehicle("Test 2")

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
    def _build_pricelist(cls, name, tiers, sequence=1):
        """A pricelist whose tiers apply to the rental product by day."""
        pricelist = cls.env["product.pricelist"].create(
            {
                "name": name,
                "currency_id": cls.env.company.currency_id.id,
                "sequence": sequence,
            }
        )
        cls.env["product.pricelist.item"].create(
            [
                {
                    "pricelist_id": pricelist.id,
                    "applied_on": "1_product",
                    "product_tmpl_id": cls.rental_product.product_tmpl_id.id,
                    "min_quantity": days,
                    "compute_price": "fixed",
                    "fixed_price": price,
                }
                for days, price in tiers
            ]
        )
        return pricelist

    @classmethod
    def _build_journal(cls, name, code, journal_type):
        return cls.env["account.journal"].create(
            {
                "name": name,
                "code": code,
                "type": journal_type,
                "company_id": cls.env.company.id,
            }
        )

    @classmethod
    def _build_vehicle(cls, label):
        brand = cls.env["fleet.vehicle.model.brand"].create({"name": "Test Brand"})
        model = cls.env["fleet.vehicle.model"].create(
            {"name": label, "brand_id": brand.id, "vehicle_type": "bike"}
        )
        return cls.env["fleet.vehicle"].create(
            {
                "rental_label": label,
                "model_id": model.id,
                "company_id": cls.env.company.id,
            }
        )

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
