# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import RentalCase


@tagged("post_install", "-at_install")
class TestPricing(RentalCase):
    """Days, tiers and the manual price."""

    # ------------------------------------------------------------------
    # Days
    # ------------------------------------------------------------------

    def test_one_day_minimum(self):
        booking = self._new_booking(days=1)
        booking.stop = booking.start + timedelta(hours=3)
        self.assertEqual(booking.rental_days, 1)

    def test_tolerance_absorbs_a_short_delay(self):
        """26 hours with a 2h tolerance is still one day."""
        booking = self._new_booking()
        booking.stop = booking.start + timedelta(hours=26)
        self.assertEqual(booking.rental_days, 1)

    def test_past_the_tolerance_a_new_day_starts(self):
        booking = self._new_booking()
        booking.stop = booking.start + timedelta(hours=27)
        self.assertEqual(booking.rental_days, 2)

    def test_exact_days(self):
        for days in (1, 3, 8, 30):
            booking = self._new_booking(days=days)
            self.assertEqual(
                booking.rental_days, days, "%s days must be charged as %s" % (days, days)
            )

    # ------------------------------------------------------------------
    # Tier borders on the General list
    # ------------------------------------------------------------------

    def test_tier_borders_general(self):
        """130 / 120 / 100 / 90 / 80 / 70 / 50 at their thresholds."""
        expected = {
            1: 130.0, 2: 130.0, 3: 130.0,
            4: 120.0, 6: 120.0,
            7: 100.0, 9: 100.0,
            10: 90.0, 13: 90.0,
            14: 80.0, 20: 80.0,
            21: 70.0, 29: 70.0,
            30: 50.0, 31: 50.0, 45: 50.0,
        }
        for days, rate in expected.items():
            self.assertEqual(
                self.Booking._tier_daily_price(self.general, days),
                rate,
                "General: %s days should be %s per day" % (days, rate),
            )

    def test_tier_borders_moradores(self):
        expected = {
            1: 80.0, 3: 80.0,
            4: 75.0, 6: 75.0,
            7: 70.0, 13: 70.0,
            14: 60.0, 29: 60.0,
            30: 40.0, 60: 40.0,
        }
        for days, rate in expected.items():
            self.assertEqual(
                self.Booking._tier_daily_price(self.moradores, days),
                rate,
                "Moradores: %s days should be %s per day" % (days, rate),
            )

    def test_over_the_longest_tier_uses_the_longest_tier(self):
        """45 days are priced with the 30-day tier, not with a 21-day one."""
        self.assertEqual(self.Booking._tier_daily_price(self.general, 45), 50.0)
        self.assertEqual(self.Booking._tier_total(self.general, 45), 45 * 50.0)

    # ------------------------------------------------------------------
    # The price lands on the booking
    # ------------------------------------------------------------------

    def test_quick_create_prices_itself_general(self):
        booking = self._new_booking(days=8)
        self.assertEqual(booking.pricelist_id, self.general)
        self.assertEqual(booking.rental_days, 8)
        self.assertEqual(booking.daily_price, 100.0)
        self.assertEqual(booking.amount_rental, 800.0)

    def test_quick_create_prices_itself_moradores(self):
        """The customer's own pricelist is proposed, not the default one."""
        booking = self._new_booking(days=8, partner=self.resident)
        self.assertEqual(booking.pricelist_id, self.moradores)
        self.assertEqual(booking.daily_price, 70.0)
        self.assertEqual(booking.amount_rental, 560.0)

    def test_price_follows_a_date_change(self):
        booking = self._new_booking(days=3)
        self.assertEqual(booking.daily_price, 130.0)
        booking.stop = booking.start + timedelta(days=8)
        self.assertEqual(booking.rental_days, 8)
        self.assertEqual(booking.daily_price, 100.0)

    # ------------------------------------------------------------------
    # Tier cap
    # ------------------------------------------------------------------

    def test_strict_tiers_by_default(self):
        """29 days cost more than 30 and that is on purpose, by default."""
        total_29 = self.Booking._tier_total(self.general, 29)
        total_30 = self.Booking._tier_total(self.general, 30)
        self.assertEqual(total_29, 29 * 70.0)
        self.assertEqual(total_30, 30 * 50.0)
        self.assertGreater(total_29, total_30)

    def test_tier_cap_never_charges_more_than_the_next_tier(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "motosrack_rental.tier_cap_enabled", "True"
        )
        total_29 = self.Booking._tier_total(self.general, 29)
        total_30 = self.Booking._tier_total(self.general, 30)
        self.assertEqual(
            total_29, total_30, "With the cap on, 29 days cannot cost more than 30."
        )

    # ------------------------------------------------------------------
    # Manual price
    # ------------------------------------------------------------------

    def test_manual_price_survives_a_date_change(self):
        booking = self._new_booking(days=3)
        booking.write({"manual_price": True, "daily_price": 55.0})
        booking.stop = booking.start + timedelta(days=8)
        self.assertEqual(booking.rental_days, 8)
        self.assertEqual(
            booking.daily_price, 55.0, "A manual price must not be recalculated."
        )
        self.assertEqual(booking.amount_rental, 440.0)

    def test_manual_price_survives_a_vehicle_change(self):
        booking = self._new_booking(days=3)
        booking.write({"manual_price": True, "daily_price": 55.0})
        booking.vehicle_id = self.moto2
        self.assertEqual(booking.daily_price, 55.0)

    def test_recompute_price_goes_back_to_the_tier(self):
        booking = self._new_booking(days=8)
        booking.write({"manual_price": True, "daily_price": 55.0})
        booking.action_recompute_price()
        self.assertFalse(booking.manual_price)
        self.assertEqual(booking.daily_price, 100.0)
        self.assertEqual(booking.amount_rental, 800.0)

    # ------------------------------------------------------------------
    # Helmets
    # ------------------------------------------------------------------

    def test_helmets_default_to_two(self):
        booking = self._new_booking()
        self.assertEqual(booking.helmet_qty, 2)

    def test_helmets_are_capped(self):
        booking = self._new_booking()
        booking.helmet_qty = 0
        self.assertEqual(booking.helmet_qty, 0)
        with self.assertRaises(ValidationError):
            booking.helmet_qty = 3

    # ------------------------------------------------------------------
    # The bike behind the resource
    # ------------------------------------------------------------------

    def test_every_bike_has_a_resource(self):
        for index in range(1, 9):
            vehicle = self.env.ref("motosrack_rental.moto_%s" % index)
            self.assertTrue(
                vehicle.resource_id,
                "Moto %s should have its own resource." % index,
            )
            self.assertEqual(vehicle.resource_id.resource_type, "material")
            self.assertEqual(vehicle.resource_id.name, "Moto %s" % index)

    def test_booking_a_vehicle_books_its_resource(self):
        booking = self._new_booking()
        self.assertEqual(booking.resource_id, self.moto1.resource_id)
