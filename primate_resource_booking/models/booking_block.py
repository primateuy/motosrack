# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class BookingBlock(models.Model):
    """A span where a resource is not available for a reason other than a booking.

    Blocks and bookings are independent records on purpose: a block may overlap
    a booking (the operator is warned, never stopped) and both stay visible on
    the timeline instead of hiding each other.

    A block with no ``stop`` is an *open* block: it lasts until someone closes
    it. That is what lets a vertical say "this resource came back and is
    pending review" without knowing in advance when the review will end.
    """

    _name = "primate.booking.block"
    _description = "Resource Block"
    _order = "start desc, id desc"

    name = fields.Char(
        string="Description",
        compute="_compute_name",
        store=True,
        readonly=False,
    )
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Resource",
        required=True,
        index=True,
        ondelete="restrict",
    )
    reason_id = fields.Many2one(
        comodel_name="primate.booking.block.reason",
        string="Reason",
        required=True,
        index=True,
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
        index=True,
        help="Leave empty for an open block: the resource stays blocked until "
             "the block is closed.",
    )
    note = fields.Text(
        string="Notes",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        related="resource_id.company_id",
        store=True,
        index=True,
    )
    color = fields.Integer(
        string="Color Index",
        related="reason_id.color",
        store=True,
    )
    blocks_availability = fields.Boolean(
        string="Blocks Availability",
        related="reason_id.blocks_availability",
        store=True,
    )
    is_open = fields.Boolean(
        string="Open Block",
        compute="_compute_is_open",
        store=True,
        help="An open block has no end date and keeps blocking the resource.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------

    @api.depends("reason_id", "resource_id")
    def _compute_name(self):
        for block in self:
            if block.reason_id and block.resource_id:
                block.name = "%s - %s" % (
                    block.resource_id.name,
                    block.reason_id.name,
                )
            else:
                block.name = block.name or False

    @api.depends("stop")
    def _compute_is_open(self):
        for block in self:
            block.is_open = not block.stop

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains("start", "stop")
    def _check_dates(self):
        for block in self:
            if block.stop and block.stop <= block.start:
                raise ValidationError(
                    _("The end of a block must be later than its start.")
                )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_close(self):
        """Close the open blocks of ``self`` by setting their end to now."""
        now = fields.Datetime.now()
        for block in self:
            if not block.stop:
                # An open block created in the future would end before it
                # starts; keep the record consistent in that corner case.
                block.stop = max(now, block.start)
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _overlap_domain(self, resource, start, stop, only_blocking=True):
        """Domain matching the blocks of ``resource`` overlapping ``[start, stop)``.

        Args:
            resource (recordset): ``resource.resource`` to look at.
            start (datetime): start of the span, included.
            stop (datetime): end of the span, excluded.
            only_blocking (bool): restrict to reasons that block availability.

        Returns:
            list: an Odoo domain.
        """
        domain = [
            ("resource_id", "=", resource.id),
            ("start", "<", stop),
            "|",
            ("stop", "=", False),
            ("stop", ">", start),
        ]
        if only_blocking:
            domain.append(("blocks_availability", "=", True))
        return domain
