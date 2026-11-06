# -*- coding: utf-8 -*-

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import RentalCase


@tagged("post_install", "-at_install")
class TestBilling(RentalCase):
    """Confirmation in one go: order, invoice, payment and balance."""

    def test_confirm_builds_the_whole_chain(self):
        booking = self._new_booking(
            days=8, payment_state="paid", payment_journal_id=self.journal_pix.id
        )
        booking.action_confirm()

        self.assertEqual(booking.state, "confirmed")
        order = booking.sale_order_id
        self.assertTrue(order, "Confirming must raise the sale order.")
        self.assertEqual(order.state, "sale")
        self.assertEqual(order.booking_id, booking)

        line = booking._rental_order_line()
        self.assertEqual(line.product_id, self.rental_product)
        self.assertEqual(line.product_uom_qty, 8, "Quantity is the number of days.")
        self.assertEqual(line.price_unit, 100.0, "The 7-day tier of the General list.")
        self.assertEqual(order.amount_untaxed, 800.0)

        invoice = order.invoice_ids
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.payment_state, "paid")
        self.assertEqual(booking.amount_total, order.amount_total)
        self.assertEqual(booking.amount_paid, order.amount_total)
        self.assertEqual(booking.amount_residual, 0.0)

    def test_confirm_blocks_the_bike(self):
        booking = self._new_booking(
            days=3, payment_state="paid", payment_journal_id=self.journal_pix.id
        )
        booking.action_confirm()
        availability = self.Booking._get_availability(
            self.moto1.resource_id, booking.start, booking.stop
        )
        self.assertFalse(availability["available"])

    def test_deposit_leaves_a_balance(self):
        booking = self._new_booking(
            days=8,
            payment_state="deposit",
            deposit_amount=300.0,
            payment_journal_id=self.journal_cash.id,
        )
        booking.action_confirm()
        invoice = booking.sale_order_id.invoice_ids
        self.assertEqual(invoice.payment_state, "partial")
        self.assertEqual(booking.amount_paid, 300.0)
        self.assertEqual(booking.amount_residual, booking.amount_total - 300.0)

    def test_pending_leaves_the_invoice_open(self):
        booking = self._new_booking(days=8, payment_state="pending")
        booking.action_confirm()
        invoice = booking.sale_order_id.invoice_ids
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(booking.amount_paid, 0.0)
        self.assertEqual(booking.amount_residual, booking.amount_total)

    def test_collecting_the_balance_later(self):
        booking = self._new_booking(days=8, payment_state="pending")
        booking.action_confirm()
        residual = booking.amount_residual
        self.assertGreater(residual, 0)

        wizard = self.env["motosrack.booking.payment"].create(
            {
                "booking_id": booking.id,
                "amount": residual,
                "journal_id": self.journal_pix.id,
            }
        )
        wizard.action_register()

        booking.invalidate_recordset(["amount_paid", "amount_residual"])
        self.assertEqual(booking.amount_residual, 0.0)
        self.assertEqual(booking.sale_order_id.invoice_ids.payment_state, "paid")

    def test_partial_collection_leaves_the_rest(self):
        booking = self._new_booking(days=8, payment_state="pending")
        booking.action_confirm()
        total = booking.amount_total
        wizard = self.env["motosrack.booking.payment"].create(
            {
                "booking_id": booking.id,
                "amount": 200.0,
                "journal_id": self.journal_cash.id,
            }
        )
        wizard.action_register()
        booking.invalidate_recordset(["amount_paid", "amount_residual"])
        self.assertEqual(booking.amount_paid, 200.0)
        self.assertEqual(booking.amount_residual, total - 200.0)

    def test_cannot_collect_more_than_owed(self):
        booking = self._new_booking(days=1, payment_state="pending")
        booking.action_confirm()
        wizard = self.env["motosrack.booking.payment"].create(
            {
                "booking_id": booking.id,
                "amount": booking.amount_total + 100.0,
                "journal_id": self.journal_cash.id,
            }
        )
        with self.assertRaises(UserError):
            wizard.action_register()

    def test_deposit_without_amount_is_refused(self):
        booking = self._new_booking(
            days=3, payment_state="deposit", payment_journal_id=self.journal_pix.id
        )
        with self.assertRaises(UserError):
            booking.action_confirm()

    def test_payment_without_journal_is_refused(self):
        booking = self._new_booking(days=3, payment_state="paid")
        with self.assertRaises(UserError):
            booking.action_confirm()

    def test_manual_price_reaches_the_order(self):
        booking = self._new_booking(days=8, payment_state="pending")
        booking.write({"manual_price": True, "daily_price": 55.0})
        booking.action_confirm()
        line = booking._rental_order_line()
        self.assertEqual(line.price_unit, 55.0)
        self.assertTrue(line.price_manual)
        self.assertEqual(booking.sale_order_id.amount_untaxed, 440.0)

    def test_confirming_without_a_customer_is_refused(self):
        booking = self.Booking.create(
            {
                "vehicle_id": self.moto1.id,
                "start": self._at(),
                "stop": self._at(days=2),
            }
        )
        with self.assertRaises(UserError):
            booking.action_confirm()
