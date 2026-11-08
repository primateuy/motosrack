# -*- coding: utf-8 -*-

import logging
from datetime import timedelta

from pytz import timezone, utc

from odoo import _, api, fields, models
from odoo.fields import Domain
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

# States in which a booking actually holds its resource. A draft booking is a
# work in progress and deliberately blocks nothing.
BLOCKING_STATES = ("confirmed", "in_use")


class Booking(models.Model):
    """A resource taken by someone over a time span.

    This model is vertical-agnostic: it has no idea about sales, invoices or
    products. Verticals add their own fields through ``_inherit`` and link the
    booking to their own document with ``res_model`` / ``res_id``.

    Time spans are half-open, ``[start, stop)``: a booking ending exactly when
    the next one starts does not overlap it. That is what makes contiguous
    bookings (an extension of an ongoing rental, a back-to-back appointment)
    possible without fudging the dates by a minute.
    """

    _name = "primate.booking"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Resource Booking"
    _order = "start desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        string="Reference",
        compute="_compute_name",
        store=True,
        readonly=False,
        help="Label shown on the agenda. Computed by default, editable.",
    )
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Resource",
        required=True,
        index=True,
        ondelete="restrict",
        check_company=True,
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        index="btree_not_null",
        ondelete="restrict",
    )
    start = fields.Datetime(
        string="Start",
        required=True,
        index=True,
        default=fields.Datetime.now,
    )
    stop = fields.Datetime(
        string="End",
        required=True,
        index=True,
    )
    duration_hours = fields.Float(
        string="Duration (hours)",
        compute="_compute_duration_hours",
        store=True,
        aggregator="sum",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("in_use", "In Use"),
            ("done", "Done"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        index=True,
        copy=False,
        tracking=True,
    )
    blocks_resource = fields.Boolean(
        string="Holds the Resource",
        compute="_compute_blocks_resource",
        store=True,
        help="Technical: whether this booking currently holds its resource.",
    )
    res_model = fields.Char(
        string="Document Model",
        index="btree_not_null",
        copy=False,
        help="Technical: model of the vertical document backing this booking.",
    )
    res_id = fields.Integer(
        string="Document ID",
        index="btree_not_null",
        copy=False,
        help="Technical: id of the vertical document backing this booking.",
    )
    color = fields.Integer(
        string="Color Index",
        default=0,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    note = fields.Text(
        string="Notes",
    )

    is_delivery_today = fields.Boolean(
        string="Starts Today",
        compute="_compute_today_flags",
        search="_search_is_delivery_today",
        help="The booking starts today in the user's timezone.",
    )
    is_return_today = fields.Boolean(
        string="Ends Today",
        compute="_compute_today_flags",
        search="_search_is_return_today",
        help="The booking ends today in the user's timezone.",
    )
    is_overdue = fields.Boolean(
        string="Overdue",
        compute="_compute_is_overdue",
        search="_search_is_overdue",
        help="The booking is still in use although its end has passed.",
    )
    conflicting_block_ids = fields.Many2many(
        comodel_name="primate.booking.block",
        string="Overlapping Blocks",
        compute="_compute_conflicting_block_ids",
        help="Blocks overlapping this booking. They do not stop the booking, "
             "they warn about it.",
    )

    # The database has the last word on double booking: a Python constraint
    # can be raced by two concurrent transactions, an exclusion constraint
    # cannot. It needs the btree_gist extension for the "resource_id WITH ="
    # part, created in init() below. If the extension is not available the
    # constraint is skipped (Odoo logs it) and the Python check still stands.
    _no_overlap = models.Constraint(
        """EXCLUDE USING gist (
            resource_id WITH =,
            tsrange("start", "stop") WITH &&
        ) WHERE (state IN ('confirmed', 'in_use'))""",
        "The resource is already taken during that period.",
    )

    def _auto_init(self):
        """Create btree_gist before the exclusion constraint is applied.

        The extension has to exist *before* ``super()``: table objects are
        applied at the end of ``_auto_init``, not in ``init``, so creating it
        there would be one step too late and the constraint would be silently
        skipped.

        Creating an extension needs enough privileges on the database. When
        that fails we log it and carry on: the Python constraint still rejects
        overlaps, we simply lose the race-condition guarantee.
        """
        try:
            with self.env.cr.savepoint(flush=False):
                self.env.cr.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        except Exception:  # noqa: BLE001 - never block the installation
            _logger.warning(
                "Could not create the btree_gist PostgreSQL extension. The "
                "exclusion constraint preventing overlapping bookings will "
                "not be installed; overlaps are still rejected by the Python "
                "constraint."
            )
        return super()._auto_init()

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends("resource_id", "partner_id")
    def _compute_name(self):
        for booking in self:
            parts = [p for p in (booking.resource_id.name, booking.partner_id.name) if p]
            booking.name = " - ".join(parts) if parts else booking.name or False

    @api.depends("start", "stop")
    def _compute_duration_hours(self):
        for booking in self:
            if booking.start and booking.stop and booking.stop > booking.start:
                delta = booking.stop - booking.start
                booking.duration_hours = delta.total_seconds() / 3600.0
            else:
                booking.duration_hours = 0.0

    @api.depends("state")
    def _compute_blocks_resource(self):
        for booking in self:
            booking.blocks_resource = booking.state in BLOCKING_STATES

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains("start", "stop")
    def _check_dates(self):
        for booking in self:
            if booking.stop <= booking.start:
                raise ValidationError(
                    _("The end of a booking must be later than its start.")
                )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    #
    # The overlap check lives here and not in an @api.constrains on purpose.
    # A constrains runs *after* the row has been written, so the exclusion
    # constraint of the database fires first and the operator gets a raw
    # psycopg2 error instead of a sentence naming the conflicting booking.
    # Checking before the write keeps the readable error first and leaves the
    # database constraint doing what it is actually good at: catching the race
    # between two concurrent transactions.

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("state", "draft") not in BLOCKING_STATES:
                continue
            self._assert_no_overlap(
                self.env["resource.resource"].browse(vals.get("resource_id")),
                fields.Datetime.to_datetime(vals.get("start")),
                fields.Datetime.to_datetime(vals.get("stop")),
            )
        return super().create(vals_list)

    def write(self, vals):
        watched = ("resource_id", "start", "stop", "state")
        if any(key in vals for key in watched):
            for booking in self:
                state = vals.get("state", booking.state)
                if state not in BLOCKING_STATES:
                    continue
                resource = (
                    self.env["resource.resource"].browse(vals["resource_id"])
                    if "resource_id" in vals
                    else booking.resource_id
                )
                start = (
                    fields.Datetime.to_datetime(vals["start"])
                    if "start" in vals
                    else booking.start
                )
                stop = (
                    fields.Datetime.to_datetime(vals["stop"])
                    if "stop" in vals
                    else booking.stop
                )
                self._assert_no_overlap(resource, start, stop, exclude_ids=booking.ids)
        return super().write(vals)

    @api.model
    def _assert_no_overlap(self, resource, start, stop, exclude_ids=None):
        """Raise when ``resource`` is already held over ``[start, stop)``."""
        if not resource or not start or not stop or stop <= start:
            # Let the dedicated constraints complain about those.
            return
        conflicts = self.search(
            self._booking_overlap_domain(resource, start, stop, exclude_ids=exclude_ids)
        )
        if conflicts:
            raise ValidationError(
                _(
                    "%(resource)s is already booked during that period:\n%(details)s",
                    resource=resource.name,
                    details="\n".join(
                        " - %s" % line for line in conflicts._availability_reasons()
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @api.model
    def _booking_overlap_domain(self, resource, start, stop, exclude_ids=None):
        """Domain matching the bookings of ``resource`` holding ``[start, stop)``.

        Args:
            resource (recordset): ``resource.resource`` to look at.
            start (datetime): start of the span, included.
            stop (datetime): end of the span, excluded.
            exclude_ids (list): booking ids to ignore, typically the one being
                validated.

        Returns:
            list: an Odoo domain.
        """
        domain = [
            ("resource_id", "=", resource.id),
            ("state", "in", BLOCKING_STATES),
            ("start", "<", stop),
            ("stop", ">", start),
        ]
        if exclude_ids:
            domain.append(("id", "not in", list(exclude_ids)))
        return domain

    def _overlapping_bookings(self):
        """Return the other bookings holding this booking's resource and span."""
        self.ensure_one()
        return self.search(
            self._booking_overlap_domain(
                self.resource_id, self.start, self.stop, exclude_ids=self.ids
            )
        )

    def _availability_reasons(self):
        """Human readable reasons why these bookings hold their resource.

        Returns:
            list: one translated string per booking.
        """
        labels = {
            "confirmed": _("Reserved"),
            "in_use": _("In use"),
        }
        reasons = []
        for booking in self:
            reasons.append(
                _(
                    "%(label)s from %(start)s to %(stop)s%(who)s",
                    label=labels.get(booking.state, booking.state),
                    start=self._format_datetime(booking.start),
                    stop=self._format_datetime(booking.stop),
                    who=_(" by %s", booking.partner_id.name) if booking.partner_id else "",
                )
            )
        return reasons

    @api.model
    def _get_availability(self, resource, start, stop, exclude_bookings=None):
        """Tell whether ``resource`` is free over ``[start, stop)``.

        This is the public entry point verticals are expected to call. It never
        raises: it reports. Deciding what to do with a conflict (refuse, warn,
        ask) belongs to the caller.

        Args:
            resource (recordset): a single ``resource.resource``.
            start (datetime): start of the span, included.
            stop (datetime): end of the span, excluded.
            exclude_bookings (recordset): bookings to ignore, typically the one
                being edited.

        Returns:
            dict: with keys
                ``available`` (bool): True when nothing holds the resource.
                ``reasons`` (list): translated strings explaining why not.
                ``bookings`` (recordset): conflicting ``primate.booking``.
                ``blocks`` (recordset): overlapping blocking
                    ``primate.booking.block``.
        """
        resource.ensure_one()
        exclude_ids = exclude_bookings.ids if exclude_bookings else []
        bookings = self.search(
            self._booking_overlap_domain(resource, start, stop, exclude_ids=exclude_ids)
        )
        blocks = self.env["primate.booking.block"].search(
            self.env["primate.booking.block"]._overlap_domain(resource, start, stop)
        )
        reasons = bookings._availability_reasons()
        for block in blocks:
            reasons.append(
                _(
                    "%(reason)s from %(start)s%(until)s",
                    reason=block.reason_id.name,
                    start=self._format_datetime(block.start),
                    until=(
                        _(" to %s", self._format_datetime(block.stop))
                        if block.stop
                        else _(" (open)")
                    ),
                )
            )
        return {
            "available": not bookings and not blocks,
            "reasons": reasons,
            "bookings": bookings,
            "blocks": blocks,
        }

    @api.model
    def _format_datetime(self, value):
        """Render a UTC datetime in the user's timezone and language."""
        if not value:
            return ""
        return fields.Datetime.context_timestamp(self, value).strftime("%d/%m/%Y %H:%M")

    def _check_availability(self):
        """Raise a readable error when one of these bookings cannot be held."""
        for booking in self:
            availability = self._get_availability(
                booking.resource_id,
                booking.start,
                booking.stop,
                exclude_bookings=booking,
            )
            if not availability["available"]:
                raise UserError(
                    _(
                        "%(resource)s is not available from %(start)s to %(stop)s:\n%(details)s",
                        resource=booking.resource_id.name,
                        start=self._format_datetime(booking.start),
                        stop=self._format_datetime(booking.stop),
                        details="\n".join(
                            " - %s" % reason for reason in availability["reasons"]
                        ),
                    )
                )
        return True

    # ------------------------------------------------------------------
    # Day of operation
    # ------------------------------------------------------------------

    @api.model
    def _today_bounds(self):
        """Return today's bounds as naive UTC datetimes.

        Datetime fields are stored in UTC while "today" is a question about the
        user's timezone, so the two ends of the local day have to be converted
        before they can be compared with the stored values. Doing it with
        ``context_today().strftime(...)`` straight inside a domain, as is
        common in Odoo, silently shifts the window by the UTC offset: in
        America/Fortaleza (UTC-3) it would include yesterday evening and miss
        the last three hours of today.

        Returns:
            tuple: ``(day_start_utc, day_end_utc)``, the end being excluded.
        """
        user_tz = timezone(self.env.user.tz or self.env.context.get("tz") or "UTC")
        local_now = fields.Datetime.now().replace(tzinfo=utc).astimezone(user_tz)
        local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_day_end = local_day_start + timedelta(days=1)
        return (
            local_day_start.astimezone(utc).replace(tzinfo=None),
            local_day_end.astimezone(utc).replace(tzinfo=None),
        )

    @api.depends("start", "stop")
    def _compute_today_flags(self):
        day_start, day_end = self._today_bounds()
        for booking in self:
            booking.is_delivery_today = bool(
                booking.start and day_start <= booking.start < day_end
            )
            booking.is_return_today = bool(
                booking.stop and day_start <= booking.stop < day_end
            )

    def _search_today(self, field_name, operator, value):
        """Shared search for the "starts/ends today" booleans.

        Odoo 19 normalises ``('field', '=', True)`` into ``('field', 'in',
        [True])`` before handing it over, and expects ``NotImplemented`` for
        the negative operators so that it can negate the positive result
        itself. Anything else and the domain blows up with "Unsupported
        operator: in".
        """
        if operator != "in":
            return NotImplemented
        day_start, day_end = self._today_bounds()
        inside = Domain(field_name, ">=", day_start) & Domain(field_name, "<", day_end)
        return self._domain_for_boolean(value, inside)

    @api.model
    def _domain_for_boolean(self, value, true_domain):
        """Turn a normalised boolean ``in`` value into a domain."""
        wants_true = True in value
        wants_false = False in value
        if wants_true and wants_false:
            return Domain.TRUE
        if wants_true:
            return true_domain
        if wants_false:
            return ~true_domain
        return Domain.FALSE

    def _search_is_delivery_today(self, operator, value):
        return self._search_today("start", operator, value)

    def _search_is_return_today(self, operator, value):
        return self._search_today("stop", operator, value)

    @api.depends("state", "stop")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for booking in self:
            booking.is_overdue = booking.state == "in_use" and booking.stop < now

    def _search_is_overdue(self, operator, value):
        if operator != "in":
            return NotImplemented
        now = fields.Datetime.now()
        overdue = Domain("state", "=", "in_use") & Domain("stop", "<", now)
        return self._domain_for_boolean(value, overdue)

    @api.depends("resource_id", "start", "stop")
    def _compute_conflicting_block_ids(self):
        Block = self.env["primate.booking.block"]
        for booking in self:
            if booking.resource_id and booking.start and booking.stop:
                booking.conflicting_block_ids = Block.search(
                    Block._overlap_domain(
                        booking.resource_id, booking.start, booking.stop
                    )
                )
            else:
                booking.conflicting_block_ids = False

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def action_confirm(self):
        """Hold the resource. Verticals extend this to bill, notify, ..."""
        self._check_availability()
        self.write({"state": "confirmed"})
        return True

    def action_start(self):
        """The resource physically left: the booking is now in use."""
        self.write({"state": "in_use"})
        return True

    def action_done(self):
        """The resource came back and the booking is closed."""
        self.write({"state": "done"})
        return True

    def action_cancel(self):
        """Release the resource without closing the booking as done."""
        self.write({"state": "cancelled"})
        return True

    def action_draft(self):
        """Send the booking back to draft, releasing the resource."""
        self.write({"state": "draft"})
        return True

    # ------------------------------------------------------------------
    # Vertical document
    # ------------------------------------------------------------------

    def action_open_document(self):
        """Open the vertical document backing this booking, if any."""
        self.ensure_one()
        if not self.res_model or not self.res_id:
            raise UserError(_("This booking is not linked to any document."))
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }

    def _link_document(self, record):
        """Point these bookings at the vertical document ``record``."""
        return self.write({"res_model": record._name, "res_id": record.id})
