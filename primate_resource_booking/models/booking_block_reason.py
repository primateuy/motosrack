# -*- coding: utf-8 -*-

from odoo import fields, models


class BookingBlockReason(models.Model):
    """Catalogue of reasons why a resource can be blocked.

    Verticals load their own reasons as data. A reason that does not block
    availability is purely informative: it still shows up on the agenda but
    it never makes ``_get_availability`` return unavailable.
    """

    _name = "primate.booking.block.reason"
    _description = "Resource Block Reason"
    _order = "sequence, name"

    name = fields.Char(
        string="Reason",
        required=True,
        translate=True,
    )
    code = fields.Char(
        string="Code",
        required=True,
        help="Technical identifier, meant to be looked up from code.",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )
    color = fields.Integer(
        string="Color Index",
        default=0,
    )
    blocks_availability = fields.Boolean(
        string="Blocks Availability",
        default=True,
        help="When enabled, a block with this reason makes the resource "
             "unavailable. When disabled the block is only informative.",
    )
    active = fields.Boolean(
        string="Active",
        default=True,
    )

    _code_uniq = models.Constraint(
        "UNIQUE(code)",
        "The code of a block reason must be unique.",
    )
