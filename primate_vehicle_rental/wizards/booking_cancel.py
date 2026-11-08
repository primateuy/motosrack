# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class BookingCancel(models.TransientModel):
    """Decides what happens with the money of a cancelled booking.

    The decision is always a human one: refund everything, refund part of it,
    or keep it. Whatever is chosen, it ends up in the chatter.
    """

    _name = "primate.rental.cancel"
    _description = "Cancel a booking"

    booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Booking",
        required=True,
        ondelete="cascade",
    )
    currency_id = fields.Many2one(related="booking_id.currency_id")
    amount_paid = fields.Monetary(
        string="Collected",
        related="booking_id.amount_paid",
        currency_field="currency_id",
    )
    decision = fields.Selection(
        selection=[
            ("refund_all", "Refund everything"),
            ("refund_partial", "Refund part of it"),
            ("keep_all", "Keep everything"),
        ],
        string="What To Do",
        required=True,
        default="refund_all",
    )
    retained_amount = fields.Monetary(
        string="Amount Kept",
        compute="_compute_retained_amount",
        store=True,
        readonly=False,
        currency_field="currency_id",
    )
    refund_amount = fields.Monetary(
        string="Amount Refunded",
        compute="_compute_refund_amount",
        currency_field="currency_id",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Refund Method",
        domain="[('type', 'in', ('bank', 'cash'))]",
    )
    reason = fields.Text(string="Reason")

    @api.depends("decision", "amount_paid")
    def _compute_retained_amount(self):
        for wizard in self:
            if wizard.decision == "refund_all":
                wizard.retained_amount = 0.0
            elif wizard.decision == "keep_all":
                wizard.retained_amount = wizard.amount_paid
            else:
                wizard.retained_amount = wizard.retained_amount or 0.0

    @api.depends("retained_amount", "amount_paid")
    def _compute_refund_amount(self):
        for wizard in self:
            wizard.refund_amount = max(
                0.0, wizard.amount_paid - wizard.retained_amount
            )

    def action_apply(self):
        """Credit the part that is not retained and pay the refund back."""
        self.ensure_one()
        booking = self.booking_id
        if self.retained_amount < 0 or self.retained_amount > self.amount_paid:
            raise UserError(
                _("The retained amount has to be between zero and what was collected.")
            )
        if self.refund_amount > 0 and not self.journal_id:
            raise UserError(_("Choose how the money is given back."))
        if self.refund_amount > 0:
            self._create_refund()
        booking.message_post(
            body=_(
                "Cancellation settled: %(kept)s kept and "
                "%(back)s refunded.%(reason)s",
                kept=booking._format_amount(self.retained_amount),
                back=booking._format_amount(self.refund_amount),
                reason=_("\nReason: %s", self.reason) if self.reason else "",
            )
        )
        return {"type": "ir.actions.act_window_close"}

    def _create_refund(self):
        """Issue the credit note for the refunded part and pay it out."""
        self.ensure_one()
        booking = self.booking_id
        invoices = booking.sale_order_id.invoice_ids.filtered(
            lambda move: move.state == "posted" and move.move_type == "out_invoice"
        )
        if not invoices:
            raise UserError(_("There is no posted invoice to credit."))
        invoice = invoices.sorted("invoice_date")[0]
        reversal = (
            self.env["account.move.reversal"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "journal_id": invoice.journal_id.id,
                    "reason": self.reason or _("Booking cancellation"),
                }
            )
        )
        action = reversal.reverse_moves()
        credit_note = self.env["account.move"].browse(action["res_id"])
        # A partial retention means the credit note is not for the whole
        # invoice: only the refunded part is credited. The existing lines are
        # scaled rather than replaced, because a line built from scratch
        # would lose its link to the sale order line and the credit note
        # would disappear from the order's invoices.
        currency = credit_note.currency_id
        if not currency.is_zero(credit_note.amount_total - self.refund_amount):
            if currency.is_zero(credit_note.amount_total):
                raise UserError(_("The credit note has nothing to scale."))
            factor = self.refund_amount / credit_note.amount_total
            for line in credit_note.invoice_line_ids:
                line.price_unit = line.price_unit * factor
            credit_note.invoice_line_ids[:1].name = _(
                "Partial refund - %s", booking.display_name
            )
        credit_note.action_post()
        booking._register_payment(
            credit_note, self.refund_amount, self.journal_id
        )
        return credit_note
