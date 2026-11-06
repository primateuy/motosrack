# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.fields import Domain

from .booking import BLOCKING_STATES


class ResourceResource(models.Model):
    """Adds the booking side of a resource.

    Kept deliberately thin: counters and shortcuts for the UI, no business
    rules. Availability itself lives on ``primate.booking._get_availability``
    so that a caller can ask about any span, not only about "right now".
    """

    _inherit = "resource.resource"

    booking_ids = fields.One2many(
        comodel_name="primate.booking",
        inverse_name="resource_id",
        string="Bookings",
    )
    booking_block_ids = fields.One2many(
        comodel_name="primate.booking.block",
        inverse_name="resource_id",
        string="Blocks",
    )
    booking_count = fields.Integer(
        string="Bookings Count",
        compute="_compute_booking_count",
    )
    is_available_now = fields.Boolean(
        string="Available Now",
        compute="_compute_is_available_now",
        search="_search_is_available_now",
        help="Whether the resource is free at this very moment.",
    )
    unavailability_reason = fields.Char(
        string="Unavailability Reason",
        compute="_compute_is_available_now",
    )

    def _compute_booking_count(self):
        counts = {
            resource.id: count
            for resource, count in self.env["primate.booking"]._read_group(
                [("resource_id", "in", self.ids)],
                groupby=["resource_id"],
                aggregates=["__count"],
            )
        }
        for resource in self:
            resource.booking_count = counts.get(resource.id, 0)

    def _compute_is_available_now(self):
        """Resolve availability for the current instant.

        Not stored on purpose: it depends on the clock, so a stored value would
        be stale the moment it is written. Filtering on it goes through
        ``_search_is_available_now``, which answers in two queries instead of
        one per resource.
        """
        now = fields.Datetime.now()
        Booking = self.env["primate.booking"]
        for resource in self:
            availability = Booking._get_availability(resource, now, now)
            resource.is_available_now = availability["available"]
            resource.unavailability_reason = (
                availability["reasons"][0] if availability["reasons"] else False
            )

    def _search_is_available_now(self, operator, value):
        # Odoo 19 normalises '=' into 'in' and expects NotImplemented for the
        # negative operators, which it then negates on its own.
        if operator != "in":
            return NotImplemented
        now = fields.Datetime.now()
        busy = self.env["primate.booking"].search(
            [
                ("state", "in", BLOCKING_STATES),
                ("start", "<=", now),
                ("stop", ">", now),
            ]
        ).resource_id
        blocked = self.env["primate.booking.block"].search(
            [
                ("blocks_availability", "=", True),
                ("start", "<=", now),
                "|",
                ("stop", "=", False),
                ("stop", ">", now),
            ]
        ).resource_id
        unavailable = busy | blocked
        wants_available = True in value
        wants_unavailable = False in value
        if wants_available and wants_unavailable:
            return Domain.TRUE
        if wants_available:
            return Domain("id", "not in", unavailable.ids)
        if wants_unavailable:
            return Domain("id", "in", unavailable.ids)
        return Domain.FALSE

    def action_view_bookings(self):
        """Open the bookings of these resources."""
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "primate_resource_booking.action_booking"
        )
        action["domain"] = [("resource_id", "in", self.ids)]
        if len(self) == 1:
            action["context"] = {"default_resource_id": self.id}
        return action
