# -*- coding: utf-8 -*-

from datetime import datetime, timedelta

import psycopg2

from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestBooking(TransactionCase):
    """Availability rules of the generic booking agenda."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The reasons returned by _get_availability are translatable, and
        # this database runs in pt_BR. The assertions below are about the
        # English source strings, so the tests speak English.
        cls.env = cls.env(context=dict(cls.env.context, lang="en_US"))
        cls.Booking = cls.env["primate.booking"]
        cls.Block = cls.env["primate.booking.block"]
        cls.resource = cls.env["resource.resource"].create(
            {"name": "Resource A", "resource_type": "material"}
        )
        cls.other_resource = cls.env["resource.resource"].create(
            {"name": "Resource B", "resource_type": "material"}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Ana"})
        # A fixed week, far from "now", so the tests never depend on the clock.
        cls.day1 = datetime(2030, 3, 11, 10, 0, 0)
        cls.day3 = cls.day1 + timedelta(days=2)
        cls.day5 = cls.day1 + timedelta(days=4)
        cls.day7 = cls.day1 + timedelta(days=6)

    def _booking(self, start, stop, resource=None, state="draft"):
        booking = self.Booking.create(
            {
                "resource_id": (resource or self.resource).id,
                "partner_id": self.partner.id,
                "start": start,
                "stop": stop,
            }
        )
        if state != "draft":
            booking.state = state
        return booking

    # ------------------------------------------------------------------
    # Dates
    # ------------------------------------------------------------------

    def test_stop_must_be_after_start(self):
        with self.assertRaises(ValidationError):
            self._booking(self.day3, self.day1)

    def test_zero_length_booking_rejected(self):
        with self.assertRaises(ValidationError):
            self._booking(self.day1, self.day1)

    def test_duration_hours(self):
        booking = self._booking(self.day1, self.day1 + timedelta(hours=30))
        self.assertEqual(booking.duration_hours, 30.0)

    # ------------------------------------------------------------------
    # A draft blocks nothing
    # ------------------------------------------------------------------

    def test_draft_does_not_block(self):
        self._booking(self.day1, self.day5)
        availability = self.Booking._get_availability(
            self.resource, self.day1, self.day5
        )
        self.assertTrue(
            availability["available"],
            "A draft booking must not hold the resource.",
        )

    def test_two_drafts_may_overlap(self):
        self._booking(self.day1, self.day5)
        # No exception: nothing is held yet.
        self._booking(self.day3, self.day7)

    def test_cancelled_does_not_block(self):
        booking = self._booking(self.day1, self.day5, state="confirmed")
        booking.action_cancel()
        availability = self.Booking._get_availability(
            self.resource, self.day1, self.day5
        )
        self.assertTrue(availability["available"])

    # ------------------------------------------------------------------
    # A confirmed booking holds the resource
    # ------------------------------------------------------------------

    def test_confirmed_blocks(self):
        self._booking(self.day1, self.day5, state="confirmed")
        availability = self.Booking._get_availability(
            self.resource, self.day3, self.day7
        )
        self.assertFalse(availability["available"])
        self.assertEqual(len(availability["bookings"]), 1)
        self.assertIn("Reserved", availability["reasons"][0])

    def test_in_use_blocks(self):
        self._booking(self.day1, self.day5, state="in_use")
        availability = self.Booking._get_availability(
            self.resource, self.day3, self.day7
        )
        self.assertFalse(availability["available"])
        self.assertIn("In use", availability["reasons"][0])

    def test_overlap_rejected_on_confirm(self):
        self._booking(self.day1, self.day5, state="confirmed")
        second = self._booking(self.day3, self.day7)
        with self.assertRaises(UserError):
            second.action_confirm()

    def test_overlap_rejected_on_write(self):
        self._booking(self.day1, self.day5, state="confirmed")
        later = self._booking(self.day5, self.day7, state="confirmed")
        with self.assertRaises(ValidationError):
            later.start = self.day3

    def test_contiguous_bookings_allowed(self):
        """Spans are half-open: ending exactly when the next starts is fine.

        This is what makes an extension of an ongoing booking possible without
        shaving a minute off the dates.
        """
        self._booking(self.day1, self.day5, state="confirmed")
        extension = self._booking(self.day5, self.day7)
        extension.action_confirm()
        self.assertEqual(extension.state, "confirmed")

    def test_other_resource_not_affected(self):
        self._booking(self.day1, self.day5, state="confirmed")
        availability = self.Booking._get_availability(
            self.other_resource, self.day1, self.day5
        )
        self.assertTrue(availability["available"])

    def test_future_booking_of_a_resource_in_use_today(self):
        """A resource out today can still be booked for a later span."""
        now = datetime.now()
        self._booking(
            now - timedelta(days=1), now + timedelta(days=1), state="in_use"
        )
        future = self._booking(now + timedelta(days=10), now + timedelta(days=12))
        future.action_confirm()
        self.assertEqual(future.state, "confirmed")

    def test_confirm_ignores_itself(self):
        """Confirming must not see the booking being confirmed as a conflict."""
        booking = self._booking(self.day1, self.day5, state="confirmed")
        booking.action_start()
        self.assertEqual(booking.state, "in_use")

    @mute_logger("odoo.sql_db")
    def test_database_rejects_overlap(self):
        """The exclusion constraint is the last line of defence.

        The Python constraint can be raced by two concurrent transactions; the
        database cannot. This bypasses the ORM on purpose to prove the
        constraint is really there.
        """
        first = self._booking(self.day1, self.day5, state="confirmed")
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT 1 FROM pg_constraint WHERE conname = 'primate_booking_no_overlap'"
        )
        if not self.env.cr.fetchone():
            self.skipTest("btree_gist is not available on this database.")
        with self.assertRaises(psycopg2.errors.ExclusionViolation):
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute(
                    """
                    INSERT INTO primate_booking
                        (resource_id, partner_id, start, stop, state,
                         company_id, create_uid, write_uid,
                         create_date, write_date)
                    VALUES (%s, %s, %s, %s, 'confirmed', %s, %s, %s,
                            now() at time zone 'utc', now() at time zone 'utc')
                    """,
                    (
                        self.resource.id,
                        self.partner.id,
                        self.day3,
                        self.day7,
                        first.company_id.id,
                        self.env.uid,
                        self.env.uid,
                    ),
                )

    # ------------------------------------------------------------------
    # Blocks
    # ------------------------------------------------------------------

    def test_block_makes_resource_unavailable(self):
        reason = self.env.ref("primate_resource_booking.block_reason_maintenance")
        self.Block.create(
            {
                "resource_id": self.resource.id,
                "reason_id": reason.id,
                "start": self.day1,
                "stop": self.day5,
            }
        )
        availability = self.Booking._get_availability(
            self.resource, self.day3, self.day7
        )
        self.assertFalse(availability["available"])
        self.assertIn("Maintenance", availability["reasons"][0])

    def test_open_block_blocks_forever(self):
        reason = self.env.ref("primate_resource_booking.block_reason_review")
        self.Block.create(
            {
                "resource_id": self.resource.id,
                "reason_id": reason.id,
                "start": self.day1,
                "stop": False,
            }
        )
        availability = self.Booking._get_availability(
            self.resource, self.day7, self.day7 + timedelta(days=365)
        )
        self.assertFalse(availability["available"])
        self.assertIn("(open)", availability["reasons"][0])

    def test_closing_a_block_frees_the_resource(self):
        reason = self.env.ref("primate_resource_booking.block_reason_review")
        block = self.Block.create(
            {
                "resource_id": self.resource.id,
                "reason_id": reason.id,
                "start": datetime.now() - timedelta(hours=1),
                "stop": False,
            }
        )
        self.assertTrue(block.is_open)
        block.action_close()
        self.assertFalse(block.is_open)
        self.assertTrue(block.stop)
        availability = self.Booking._get_availability(
            self.resource,
            datetime.now() + timedelta(hours=1),
            datetime.now() + timedelta(days=1),
        )
        self.assertTrue(availability["available"])

    def test_non_blocking_reason_is_informative_only(self):
        reason = self.env.ref("primate_resource_booking.block_reason_note")
        self.Block.create(
            {
                "resource_id": self.resource.id,
                "reason_id": reason.id,
                "start": self.day1,
                "stop": self.day5,
            }
        )
        availability = self.Booking._get_availability(
            self.resource, self.day1, self.day5
        )
        self.assertTrue(
            availability["available"],
            "A reason that does not block availability must not block it.",
        )

    def test_block_over_a_booking_is_allowed_and_warned(self):
        """Blocks and bookings are independent: overlapping is allowed.

        The operator is warned through ``conflicting_block_ids``, never
        stopped, and both records keep existing side by side.
        """
        booking = self._booking(self.day1, self.day5, state="confirmed")
        reason = self.env.ref("primate_resource_booking.block_reason_maintenance")
        block = self.Block.create(
            {
                "resource_id": self.resource.id,
                "reason_id": reason.id,
                "start": self.day3,
                "stop": self.day7,
            }
        )
        booking.invalidate_recordset(["conflicting_block_ids"])
        self.assertIn(block, booking.conflicting_block_ids)
        self.assertEqual(booking.state, "confirmed", "The booking must survive.")
        self.assertTrue(block.exists(), "The block must survive.")

    def test_block_end_must_be_after_start(self):
        reason = self.env.ref("primate_resource_booking.block_reason_review")
        with self.assertRaises(ValidationError):
            self.Block.create(
                {
                    "resource_id": self.resource.id,
                    "reason_id": reason.id,
                    "start": self.day5,
                    "stop": self.day1,
                }
            )

    # ------------------------------------------------------------------
    # Day of operation
    # ------------------------------------------------------------------

    def test_today_flags_follow_the_user_timezone(self):
        """"Today" is a question about the user's timezone, not about UTC.

        In America/Fortaleza (UTC-3) the local day runs from 03:00 UTC to
        03:00 UTC the next day. A booking ending at 01:00 UTC belongs to the
        *previous* local day, and one ending at 02:00 UTC tomorrow still
        belongs to today.
        """
        self.env.user.tz = "America/Fortaleza"
        today_utc = datetime.combine(
            datetime.now().date(), datetime.min.time()
        )
        # 23:00 local today  ==  02:00 UTC tomorrow
        late_tonight = today_utc + timedelta(days=1, hours=2)
        booking = self._booking(late_tonight - timedelta(days=3), late_tonight)
        booking.invalidate_recordset(["is_return_today", "is_delivery_today"])
        self.assertTrue(
            booking.is_return_today,
            "A return at 23:00 local time is still a return for today.",
        )
        self.assertIn(booking, self.Booking.search([("is_return_today", "=", True)]))

    def test_overdue_detection(self):
        now = datetime.now()
        late = self._booking(
            now - timedelta(days=3), now - timedelta(hours=2), state="in_use"
        )
        on_time = self._booking(
            now - timedelta(days=3),
            now + timedelta(hours=2),
            resource=self.other_resource,
            state="in_use",
        )
        self.assertTrue(late.is_overdue)
        self.assertFalse(on_time.is_overdue)
        overdue = self.Booking.search([("is_overdue", "=", True)])
        self.assertIn(late, overdue)
        self.assertNotIn(on_time, overdue)

    # ------------------------------------------------------------------
    # Resource side
    # ------------------------------------------------------------------

    def test_resource_availability_now(self):
        now = datetime.now()
        self._booking(
            now - timedelta(hours=1), now + timedelta(hours=1), state="in_use"
        )
        self.resource.invalidate_recordset(["is_available_now"])
        self.assertFalse(self.resource.is_available_now)
        self.assertTrue(self.other_resource.is_available_now)
        free = self.env["resource.resource"].search(
            [("is_available_now", "=", True), ("id", "in", (self.resource | self.other_resource).ids)]
        )
        self.assertEqual(free, self.other_resource)

    def test_booking_count(self):
        self._booking(self.day1, self.day3)
        self._booking(self.day5, self.day7)
        self.resource.invalidate_recordset(["booking_count"])
        self.assertEqual(self.resource.booking_count, 2)

    # ------------------------------------------------------------------
    # Vertical document link
    # ------------------------------------------------------------------

    def test_link_document(self):
        booking = self._booking(self.day1, self.day5)
        booking._link_document(self.partner)
        self.assertEqual(booking.res_model, "res.partner")
        self.assertEqual(booking.res_id, self.partner.id)
        action = booking.action_open_document()
        self.assertEqual(action["res_model"], "res.partner")
        self.assertEqual(action["res_id"], self.partner.id)

    def test_open_document_without_link(self):
        booking = self._booking(self.day1, self.day5)
        with self.assertRaises(UserError):
            booking.action_open_document()
