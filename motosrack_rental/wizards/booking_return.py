# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .booking_deliver import FUEL_LEVELS


class BookingReturn(models.TransientModel):
    """Takes the bike back and says what came back with it."""

    _name = "motosrack.booking.return"
    _description = "Return the bike"

    booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Booking",
        required=True,
        ondelete="cascade",
    )
    vehicle_id = fields.Many2one(related="booking_id.vehicle_id")
    helmets_delivered = fields.Integer(related="booking_id.helmets_delivered")
    return_datetime = fields.Datetime(
        string="Return Date and Time",
        required=True,
        default=fields.Datetime.now,
    )
    helmets_returned = fields.Integer(
        string="Helmets Returned",
        compute="_compute_helmets",
        store=True,
        readonly=False,
    )
    helmets_lost = fields.Integer(
        string="Helmets Lost or Damaged",
        compute="_compute_helmets_lost",
        store=True,
        readonly=False,
        help="They do not go back to available stock: they are written off "
             "to the loss location so the shortage shows in the counts.",
    )
    odometer = fields.Float(string="Mileage")
    fuel_level = fields.Selection(selection=FUEL_LEVELS, string="Fuel")
    note = fields.Text(string="Notes")
    attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        string="Photos",
    )
    late_warning = fields.Text(
        string="Delay",
        compute="_compute_late_warning",
    )

    @api.depends("booking_id")
    def _compute_helmets(self):
        for wizard in self:
            wizard.helmets_returned = wizard.booking_id.helmets_delivered

    @api.depends("helmets_returned", "booking_id")
    def _compute_helmets_lost(self):
        for wizard in self:
            wizard.helmets_lost = max(
                0, wizard.booking_id.helmets_delivered - wizard.helmets_returned
            )

    @api.depends("booking_id", "return_datetime")
    def _compute_late_warning(self):
        tolerance = self.env["motosrack.rental.parameters"]._param_float(
            "late_tolerance_hours"
        )
        for wizard in self:
            booking = wizard.booking_id
            if not booking or not wizard.return_datetime or not booking.stop:
                wizard.late_warning = False
                continue
            hours = (
                wizard.return_datetime - booking.stop
            ).total_seconds() / 3600.0 - tolerance
            if hours <= 0:
                wizard.late_warning = False
                continue
            wizard.late_warning = _(
                "The return is %(hours).1f hours late. A surcharge will be "
                "suggested on the order.",
                hours=hours,
            )

    def action_return(self):
        self.ensure_one()
        total = self.helmets_returned + self.helmets_lost
        if total > self.booking_id.helmets_delivered:
            raise UserError(
                _(
                    "Only %(delivered)s helmet(s) went out; %(total)s cannot "
                    "come back.",
                    delivered=self.booking_id.helmets_delivered,
                    total=total,
                )
            )
        self.booking_id._do_return(
            self.return_datetime,
            self.helmets_returned,
            helmets_lost=self.helmets_lost,
            note=self.note,
            odometer=self.odometer,
            fuel=self.fuel_level,
        )
        self._attach_photos()
        return {"type": "ir.actions.act_window_close"}

    def _attach_photos(self):
        self.ensure_one()
        if not self.attachment_ids:
            return False
        self.attachment_ids.write(
            {"res_model": "primate.booking", "res_id": self.booking_id.id}
        )
        self.booking_id.message_post(
            body=_("Photos of the return."),
            attachment_ids=self.attachment_ids.ids,
        )
        return True
