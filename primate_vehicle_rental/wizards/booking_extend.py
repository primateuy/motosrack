# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.primate_booking import EXTENSION_CRITERIA, PAYMENT_STATES


class BookingExtend(models.TransientModel):
    """Extends an ongoing rental: the customer simply keeps the vehicle."""

    _name = "primate.rental.extend"
    _description = "Extend a rental"

    booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Booking",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(related="booking_id.currency_id")
    current_stop = fields.Datetime(
        string="Current End",
        related="booking_id.stop",
    )
    new_stop = fields.Datetime(
        string="New End",
        required=True,
    )
    criterion = fields.Selection(
        selection=EXTENSION_CRITERIA,
        string="Criterion",
        required=True,
        default=lambda self: self.env["primate.rental.parameters"]._param(
            "default_extension_criterion"
        ),
    )
    new_days = fields.Integer(
        string="New Days",
        compute="_compute_preview",
    )
    chain_days = fields.Integer(
        string="Accumulated Days",
        compute="_compute_preview",
    )
    amount = fields.Monetary(
        string="Extension Amount",
        compute="_compute_preview",
        currency_field="currency_id",
    )
    daily_price = fields.Monetary(
        string="Daily Price Applied",
        compute="_compute_preview",
        currency_field="currency_id",
    )
    conflict_warning = fields.Text(
        string="Warnings",
        compute="_compute_preview",
    )
    payment_state = fields.Selection(
        selection=PAYMENT_STATES,
        string="Payment Status",
        default="pending",
        required=True,
    )
    deposit_amount = fields.Monetary(
        string="Deposit Amount",
        currency_field="currency_id",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Payment Method",
        domain="[('type', 'in', ('bank', 'cash'))]",
    )

    @api.depends("booking_id", "new_stop", "criterion")
    def _compute_preview(self):
        """Show what the extension will cost before anything is created."""
        for wizard in self:
            booking = wizard.booking_id
            if not booking or not wizard.new_stop or wizard.new_stop <= booking.stop:
                wizard.new_days = 0
                wizard.chain_days = booking.chain_days if booking else 0
                wizard.amount = 0.0
                wizard.daily_price = 0.0
                wizard.conflict_warning = False
                continue
            days, amount, daily = booking._extension_amount(
                wizard.new_stop, wizard.criterion
            )
            wizard.new_days = days
            wizard.chain_days = booking.chain_days + days
            wizard.amount = amount
            wizard.daily_price = daily
            availability = booking._get_availability(
                booking.resource_id,
                booking.stop,
                wizard.new_stop,
                exclude_bookings=booking,
            )
            wizard.conflict_warning = (
                "\n".join(availability["reasons"])
                if availability["reasons"]
                else False
            )

    def action_extend(self):
        self.ensure_one()
        if self.payment_state == "deposit" and self.deposit_amount <= 0:
            raise UserError(_("A deposit needs an amount greater than zero."))
        if self.payment_state in ("paid", "deposit") and not self.journal_id:
            raise UserError(_("Choose how the extension is being paid."))
        extension = self.booking_id._create_extension(
            self.new_stop,
            self.criterion,
            payment_state=self.payment_state,
            journal=self.journal_id,
            deposit=self.deposit_amount,
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Extension"),
            "res_model": "primate.booking",
            "res_id": extension.id,
            "view_mode": "form",
        }
