# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import RentalCase


@tagged("post_install", "-at_install")
class TestOperations(RentalCase):
    """Delivery, return, helmets, delays, changes and cancellations."""

    def _confirmed(self, days=3, **extra):
        values = {"payment_state": "paid", "payment_journal_id": self.journal_pix.id}
        values.update(extra)
        booking = self._new_booking(days=days, **values)
        booking.action_confirm()
        return booking

    # ------------------------------------------------------------------
    # Delivery and return
    # ------------------------------------------------------------------

    def test_delivery_sets_the_booking_in_use(self):
        booking = self._confirmed()
        self._receive_helmets(10)
        wizard = self.env["motosrack.booking.deliver"].create(
            {
                "booking_id": booking.id,
                "delivery_datetime": booking.start,
                "helmet_qty": 2,
                "odometer": 1000.0,
                "fuel_level": "full",
            }
        )
        wizard.action_deliver()
        self.assertEqual(booking.state, "in_use")
        self.assertEqual(booking.delivery_datetime, booking.start)
        self.assertEqual(booking.helmets_delivered, 2)
        self.assertEqual(booking.vehicle_id.odometer, 1000.0)

    def test_helmets_leave_stock_and_come_back(self):
        stock = self.env.ref("stock.stock_location_stock")
        rented = self.env.ref("motosrack_rental.location_helmets_rented")
        self._receive_helmets(10)
        self.assertEqual(self._stock_qty(stock), 10)

        booking = self._confirmed()
        booking._do_deliver(booking.start, 2)
        self.assertEqual(self._stock_qty(stock), 8, "Two helmets left the shop.")
        self.assertEqual(self._stock_qty(rented), 2)

        booking._do_return(booking.stop, 2)
        self.assertEqual(self._stock_qty(stock), 10, "Both came back.")
        self.assertEqual(self._stock_qty(rented), 0)

    def test_a_missing_helmet_does_not_go_back_to_stock(self):
        stock = self.env.ref("stock.stock_location_stock")
        rented = self.env.ref("motosrack_rental.location_helmets_rented")
        lost = self.env.ref("motosrack_rental.location_helmets_lost")
        self._receive_helmets(10)

        booking = self._confirmed()
        booking._do_deliver(booking.start, 2)
        booking._do_return(booking.stop, 1, helmets_lost=1)

        self.assertEqual(
            self._stock_qty(stock), 9, "Only the helmet that came back is available."
        )
        self.assertEqual(self._stock_qty(rented), 0)
        self.assertEqual(
            self._stock_qty(lost), 1,
            "The missing helmet ends up in the loss location.",
        )
        self.assertEqual(
            lost.usage, "inventory",
            "The loss location keeps it out of on-hand stock.",
        )
        self.assertEqual(
            self.helmet_product.qty_available, 9,
            "Only nine helmets are really available.",
        )
        self.assertEqual(booking.helmets_returned, 1)
        self.assertEqual(booking.helmets_pending, 1)

    def test_cannot_return_more_helmets_than_went_out(self):
        self._receive_helmets(10)
        booking = self._confirmed()
        booking._do_deliver(booking.start, 1)
        wizard = self.env["motosrack.booking.return"].create(
            {
                "booking_id": booking.id,
                "return_datetime": booking.stop,
                "helmets_returned": 2,
                "helmets_lost": 1,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_return()

    # ------------------------------------------------------------------
    # Review block
    # ------------------------------------------------------------------

    def test_return_opens_a_review_block(self):
        self._receive_helmets(10)
        booking = self._confirmed()
        booking._do_deliver(booking.start, 2)
        booking._do_return(booking.stop, 2)

        self.assertEqual(booking.state, "done")
        block = booking.review_block_id
        self.assertTrue(block, "Returning must block the bike for review.")
        self.assertTrue(block.is_open, "The review block has no end date.")
        self.assertEqual(block.start, booking.stop)

        availability = self.Booking._get_availability(
            self.moto1.resource_id,
            booking.stop + timedelta(days=1),
            booking.stop + timedelta(days=2),
        )
        self.assertFalse(
            availability["available"], "A bike under review is not available."
        )

    def test_releasing_the_bike_closes_the_block(self):
        self._receive_helmets(10)
        booking = self._confirmed()
        booking._do_deliver(booking.start, 2)
        booking._do_return(booking.stop, 2)
        booking.action_release_vehicle()

        self.assertFalse(booking.review_block_id.is_open)
        availability = self.Booking._get_availability(
            self.moto1.resource_id,
            booking.stop + timedelta(days=1),
            booking.stop + timedelta(days=2),
        )
        self.assertTrue(availability["available"])

    # ------------------------------------------------------------------
    # Late returns
    # ------------------------------------------------------------------

    def test_late_return_suggests_a_surcharge(self):
        self._receive_helmets(10)
        booking = self._confirmed(days=3)
        booking._do_deliver(booking.start, 2)
        # A day and a half past the planned end, well beyond the tolerance.
        booking._do_return(booking.stop + timedelta(hours=36), 2)

        late_product = self.env.ref(
            "motosrack_rental.product_late_fee"
        ).product_variant_id
        line = booking.sale_order_id.order_line.filtered(
            lambda l: l.product_id == late_product
        )
        self.assertTrue(line, "A late return must suggest a surcharge line.")
        self.assertEqual(line.product_uom_qty, 2, "36h late are two extra days.")
        self.assertEqual(line.price_unit, booking.daily_price)

    def test_a_return_within_the_tolerance_costs_nothing_extra(self):
        self._receive_helmets(10)
        booking = self._confirmed(days=3)
        booking._do_deliver(booking.start, 2)
        booking._do_return(booking.stop + timedelta(hours=1), 2)

        late_product = self.env.ref(
            "motosrack_rental.product_late_fee"
        ).product_variant_id
        self.assertFalse(
            booking.sale_order_id.order_line.filtered(
                lambda l: l.product_id == late_product
            )
        )

    def test_late_return_warns_about_the_next_booking(self):
        self._receive_helmets(10)
        booking = self._confirmed(days=3)
        following = self._new_booking(
            days=2,
            start=booking.stop,
            payment_state="pending",
        )
        following.action_confirm()

        booking._do_deliver(booking.start, 2)
        booking._do_return(booking.stop + timedelta(hours=36), 2)

        self.assertTrue(
            following.activity_ids,
            "The booking being eaten into must get an activity.",
        )

    def test_cron_flags_a_bike_that_is_still_out(self):
        now = datetime.now()
        booking = self._new_booking(
            days=2,
            start=now - timedelta(days=3),
            payment_state="pending",
        )
        booking.action_confirm()
        booking.action_start()
        following = self._new_booking(
            days=2, start=now + timedelta(hours=1), payment_state="pending"
        )
        following.action_confirm()

        self.Booking._cron_check_overdue_bookings()
        self.assertTrue(booking.activity_ids, "The overdue booking must be flagged.")

    # ------------------------------------------------------------------
    # Changes
    # ------------------------------------------------------------------

    def test_changing_the_bike_revalidates_availability(self):
        booking = self._confirmed(days=3)
        other = self._new_booking(
            days=3, vehicle=self.moto2, start=booking.start, payment_state="pending"
        )
        other.action_confirm()
        with self.assertRaises(Exception):
            booking.vehicle_id = self.moto2

    def test_changing_the_bike_to_a_free_one_works(self):
        booking = self._confirmed(days=3)
        booking.vehicle_id = self.moto2
        self.assertEqual(booking.resource_id, self.moto2.resource_id)
        availability = self.Booking._get_availability(
            self.moto1.resource_id, booking.start, booking.stop
        )
        self.assertTrue(availability["available"], "The first bike is free again.")

    def test_changing_the_dates_warns_about_the_invoiced_difference(self):
        booking = self._confirmed(days=3)
        messages_before = len(booking.message_ids)
        booking.stop = booking.start + timedelta(days=8)
        self.assertGreater(
            len(booking.message_ids),
            messages_before,
            "A change that no longer matches the invoice must say so.",
        )

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def test_cancelling_frees_the_bike(self):
        booking = self._confirmed(days=3)
        booking.action_cancel()
        self.assertEqual(booking.state, "cancelled")
        availability = self.Booking._get_availability(
            self.moto1.resource_id, booking.start, booking.stop
        )
        self.assertTrue(availability["available"])

    def test_cancelling_an_ongoing_rental_is_refused(self):
        self._receive_helmets(10)
        booking = self._confirmed(days=3)
        booking._do_deliver(booking.start, 2)
        with self.assertRaises(UserError):
            booking.action_cancel()

    def test_cancellation_with_partial_retention(self):
        booking = self._confirmed(days=8)
        self.assertEqual(booking.amount_paid, 800.0)
        booking.action_cancel()

        wizard = self.env["motosrack.booking.cancel"].create(
            {
                "booking_id": booking.id,
                "decision": "refund_partial",
                "retained_amount": 200.0,
                "journal_id": self.journal_pix.id,
                "reason": "Cancelación tardía",
            }
        )
        self.assertEqual(wizard.refund_amount, 600.0)
        wizard.action_apply()

        credit_notes = booking.sale_order_id.invoice_ids.filtered(
            lambda m: m.move_type == "out_refund"
        )
        self.assertTrue(credit_notes, "The refunded part needs a credit note.")
        self.assertEqual(credit_notes.state, "posted")
        self.assertEqual(credit_notes.amount_total, 600.0)
        booking.invalidate_recordset(["amount_paid"])
        self.assertEqual(
            booking.amount_paid, 200.0, "Only the retained part stays collected."
        )

    def test_cancellation_keeping_everything_issues_nothing(self):
        booking = self._confirmed(days=8)
        booking.action_cancel()
        wizard = self.env["motosrack.booking.cancel"].create(
            {"booking_id": booking.id, "decision": "keep_all"}
        )
        self.assertEqual(wizard.retained_amount, 800.0)
        self.assertEqual(wizard.refund_amount, 0.0)
        wizard.action_apply()
        self.assertFalse(
            booking.sale_order_id.invoice_ids.filtered(
                lambda m: m.move_type == "out_refund"
            )
        )

    # ------------------------------------------------------------------
    # Blocks next to bookings
    # ------------------------------------------------------------------

    def test_a_block_may_overlap_a_booking(self):
        booking = self._confirmed(days=5)
        reason = self.env.ref("motosrack_rental.block_reason_cleaning")
        block = self.Block.create(
            {
                "resource_id": booking.resource_id.id,
                "reason_id": reason.id,
                "start": booking.start + timedelta(days=1),
                "stop": booking.start + timedelta(days=2),
            }
        )
        booking.invalidate_recordset(["conflicting_block_ids"])
        self.assertIn(block, booking.conflicting_block_ids, "The operator is warned.")
        self.assertEqual(booking.state, "confirmed", "The booking survives.")
        self.assertTrue(block.exists(), "The block survives.")
