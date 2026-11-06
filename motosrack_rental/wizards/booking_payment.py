# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BookingPayment(models.TransientModel):
    """Collects a balance left open on a booking."""

    _name = "motosrack.booking.payment"
    _description = "Register a booking payment"

    booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Booking",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(
        related="booking_id.currency_id",
    )
    amount_residual = fields.Monetary(
        string="Balance",
        related="booking_id.chain_amount_residual",
        currency_field="currency_id",
    )
    amount = fields.Monetary(
        string="Amount to Collect",
        compute="_compute_amount",
        store=True,
        readonly=False,
        required=True,
        currency_field="currency_id",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Payment Method",
        compute="_compute_journal_id",
        store=True,
        readonly=False,
        required=True,
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    payment_date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
    )

    @api.depends("booking_id")
    def _compute_amount(self):
        for wizard in self:
            wizard.amount = wizard.booking_id.chain_amount_residual

    @api.depends("booking_id")
    def _compute_journal_id(self):
        for wizard in self:
            wizard.journal_id = wizard.booking_id.payment_journal_id

    def action_register(self):
        """Spread the amount over the open invoices of the chain, oldest first."""
        self.ensure_one()
        if self.amount <= 0:
            raise UserError(_("The amount has to be greater than zero."))
        booking = self.booking_id
        invoices = booking._open_invoices()
        if not invoices:
            raise UserError(_("There is no open invoice to collect."))
        # Checked before anything is created: raising halfway through would
        # roll the payments back anyway, but the operator would be left
        # guessing what did and did not happen.
        collectable = sum(invoices.mapped("amount_residual"))
        if self.amount > collectable:
            raise UserError(
                _(
                    "The open invoices only owe %(amount)s.",
                    amount=booking._format_amount(collectable),
                )
            )
        remaining = self.amount
        for invoice in invoices:
            if remaining <= 0:
                break
            share = min(remaining, invoice.amount_residual)
            if share <= 0:
                continue
            booking._register_payment(
                invoice, share, self.journal_id, payment_date=self.payment_date
            )
            remaining -= share
        booking.message_post(
            body=_(
                "Collected %(amount)s through %(journal)s.",
                amount=booking._format_amount(self.amount),
                journal=self.journal_id.name,
            )
        )
        return {"type": "ir.actions.act_window_close"}
