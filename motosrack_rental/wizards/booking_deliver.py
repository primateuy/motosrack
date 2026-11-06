# -*- coding: utf-8 -*-

from odoo import _, api, fields, models

FUEL_LEVELS = [
    ("empty", "Empty"),
    ("quarter", "1/4"),
    ("half", "1/2"),
    ("three_quarters", "3/4"),
    ("full", "Full"),
]


class BookingDeliver(models.TransientModel):
    """Hands the bike over and records what actually left the shop."""

    _name = "motosrack.booking.deliver"
    _description = "Deliver the bike"

    booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Booking",
        required=True,
        ondelete="cascade",
    )
    vehicle_id = fields.Many2one(related="booking_id.vehicle_id")
    delivery_datetime = fields.Datetime(
        string="Delivery Date and Time",
        required=True,
        default=fields.Datetime.now,
        help="Defaults to now, editable: the paperwork often happens later "
             "than the bike actually leaving.",
    )
    helmet_qty = fields.Integer(
        string="Helmets Delivered",
        compute="_compute_helmet_qty",
        store=True,
        readonly=False,
    )
    odometer = fields.Float(string="Mileage")
    fuel_level = fields.Selection(selection=FUEL_LEVELS, string="Fuel")
    note = fields.Text(string="Notes")
    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        string="Photos",
        help="Photos of the bike as it leaves.",
    )

    @api.depends("booking_id")
    def _compute_helmet_qty(self):
        for wizard in self:
            wizard.helmet_qty = wizard.booking_id.helmet_qty

    def action_deliver(self):
        self.ensure_one()
        self.booking_id._do_deliver(
            self.delivery_datetime,
            self.helmet_qty,
            note=self.note,
            odometer=self.odometer,
            fuel=self.fuel_level,
        )
        self._attach_photos()
        return {"type": "ir.actions.act_window_close"}

    def _attach_photos(self):
        """Move the uploaded photos onto the booking so they survive the wizard."""
        self.ensure_one()
        if not self.attachment_ids:
            return False
        self.attachment_ids.write(
            {
                "res_model": "primate.booking",
                "res_id": self.booking_id.id,
            }
        )
        self.booking_id.message_post(
            body=_("Photos of the delivery."),
            attachment_ids=self.attachment_ids.ids,
        )
        return True
