# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import RentalCase


@tagged("post_install", "-at_install")
class TestExtension(RentalCase):
    """The three extension criteria, on the case the business specified.

    Eight days rented on the General list cost R$800 (the 7-day tier at
    R$100). Extending by another eight days takes the chain to sixteen,
    which lands on the 14-day tier at R$80. From there:

    * A. recalculate:  16 x 80 - 800 = 480
    * B. accumulated:   8 x 80       = 640
    * C. independent:   8 x 100      = 800
    """

    def _rented_eight_days(self):
        booking = self._new_booking(
            days=8, payment_state="paid", payment_journal_id=self.journal_pix.id
        )
        booking.action_confirm()
        self.assertEqual(booking.amount_total, 800.0)
        return booking

    def _extend(self, booking, days, criterion):
        wizard = self.env["primate.rental.extend"].create(
            {
                "booking_id": booking.id,
                "new_stop": booking.stop + timedelta(days=days),
                "criterion": criterion,
                "payment_state": "pending",
            }
        )
        wizard.action_extend()
        return booking.child_booking_ids[-1]

    # ------------------------------------------------------------------
    # The mandatory case
    # ------------------------------------------------------------------

    def test_criterion_a_recalculate(self):
        booking = self._rented_eight_days()
        extension = self._extend(booking, 8, "recalculate")
        self.assertEqual(extension.amount_total, 480.0)

    def test_criterion_b_accumulated(self):
        booking = self._rented_eight_days()
        extension = self._extend(booking, 8, "accumulated")
        self.assertEqual(extension.amount_total, 640.0)

    def test_criterion_c_independent(self):
        booking = self._rented_eight_days()
        extension = self._extend(booking, 8, "independent")
        self.assertEqual(extension.amount_total, 800.0)

    def test_default_criterion_is_b(self):
        self.assertEqual(
            self.params._param("default_extension_criterion"), "accumulated"
        )

    # ------------------------------------------------------------------
    # Shape of the extension
    # ------------------------------------------------------------------

    def test_extension_is_contiguous_and_linked(self):
        booking = self._rented_eight_days()
        extension = self._extend(booking, 8, "accumulated")
        self.assertEqual(
            extension.start, booking.stop, "The extension starts where the rental ends."
        )
        self.assertEqual(extension.vehicle_id, booking.vehicle_id)
        self.assertEqual(extension.parent_booking_id, booking)
        self.assertEqual(extension.root_booking_id, booking)
        self.assertEqual(extension.state, "confirmed")
        self.assertEqual(
            extension.sale_order_id.rental_parent_id,
            booking.sale_order_id,
            "The new order points at the original one.",
        )

    def test_extension_does_not_touch_the_issued_invoice(self):
        booking = self._rented_eight_days()
        invoice = booking.sale_order_id.invoice_ids
        amount_before = invoice.amount_total
        self._extend(booking, 8, "recalculate")
        self.assertEqual(
            invoice.amount_total,
            amount_before,
            "An invoice already issued is never modified.",
        )
        self.assertEqual(invoice.state, "posted")

    def test_extension_needs_no_physical_handover(self):
        """The vehicle stays with the customer: no delivery, no return."""
        booking = self._rented_eight_days()
        booking._do_deliver(booking.start, 2)
        extension = self._extend(booking, 4, "accumulated")
        self.assertEqual(booking.state, "in_use")
        self.assertFalse(extension.delivery_datetime)
        self.assertFalse(booking.return_datetime)

    def test_extension_is_refused_when_the_vehicle_is_taken(self):
        booking = self._rented_eight_days()
        later = self._new_booking(
            days=2,
            start=booking.stop + timedelta(days=1),
            payment_state="pending",
        )
        later.action_confirm()
        with self.assertRaises(UserError):
            self._extend(booking, 5, "accumulated")

    # ------------------------------------------------------------------
    # Chains
    # ------------------------------------------------------------------

    def test_chain_of_two_extensions(self):
        """Days accumulate across the whole chain, not pair by pair."""
        booking = self._rented_eight_days()
        first = self._extend(booking, 8, "accumulated")
        self.assertEqual(first.amount_total, 640.0)

        # 16 + 6 = 22 days, which reaches the 21-day tier at R$70.
        second = self._extend(first, 6, "accumulated")
        self.assertEqual(second.amount_total, 6 * 70.0)

        self.assertEqual(second.root_booking_id, booking)
        self.assertEqual(second.parent_booking_id, first)
        self.assertEqual(len(booking._chain_bookings()), 3)
        self.assertEqual(booking.chain_days, 8 + 8 + 6)

    def test_chain_amounts_add_up(self):
        booking = self._rented_eight_days()
        extension = self._extend(booking, 8, "accumulated")
        booking.invalidate_recordset(
            ["chain_amount_total", "chain_amount_paid", "chain_amount_residual"]
        )
        self.assertEqual(booking.chain_amount_total, 800.0 + 640.0)
        self.assertEqual(booking.chain_amount_paid, 800.0)
        self.assertEqual(booking.chain_amount_residual, 640.0)
        self.assertEqual(
            extension.chain_amount_total,
            booking.chain_amount_total,
            "Every link of the chain reports the same chain totals.",
        )

    def test_recalculate_on_a_chain_nets_out_everything_invoiced(self):
        booking = self._rented_eight_days()
        first = self._extend(booking, 8, "accumulated")
        # Chain invoiced so far: 800 + 640 = 1440. Twenty-two days at the
        # 21-day tier are 22 x 70 = 1540, so A charges the difference.
        second = self._extend(first, 6, "recalculate")
        self.assertEqual(second.amount_total, 22 * 70.0 - 1440.0)

    def test_extension_must_move_the_end_forward(self):
        booking = self._rented_eight_days()
        with self.assertRaises(UserError):
            booking._create_extension(booking.stop, "accumulated")

    def test_extension_can_be_collected_on_the_spot(self):
        booking = self._rented_eight_days()
        wizard = self.env["primate.rental.extend"].create(
            {
                "booking_id": booking.id,
                "new_stop": booking.stop + timedelta(days=8),
                "criterion": "accumulated",
                "payment_state": "paid",
                "journal_id": self.journal_cash.id,
            }
        )
        wizard.action_extend()
        extension = booking.child_booking_ids[-1]
        self.assertEqual(extension.amount_paid, 640.0)
        self.assertEqual(extension.amount_residual, 0.0)
