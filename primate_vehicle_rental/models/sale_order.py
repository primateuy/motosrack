# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class SaleOrder(models.Model):
    """Links a sale order back to the booking that raised it."""

    _inherit = "sale.order"

    booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Booking",
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Vehicle",
        related="booking_id.vehicle_id",
        store=True,
    )
    rental_parent_id = fields.Many2one(
        comodel_name="sale.order",
        string="Original Order",
        copy=False,
        index="btree_not_null",
        ondelete="set null",
        help="For an extension: the order of the rental being extended.",
    )
    rental_child_ids = fields.One2many(
        comodel_name="sale.order",
        inverse_name="rental_parent_id",
        string="Extensions",
    )
    rental_chain_total = fields.Monetary(
        string="Contracted Total (chain)",
        compute="_compute_rental_chain_amounts",
    )
    rental_chain_paid = fields.Monetary(
        string="Collected Total (chain)",
        compute="_compute_rental_chain_amounts",
    )
    rental_chain_residual = fields.Monetary(
        string="Balance (chain)",
        compute="_compute_rental_chain_amounts",
    )

    @api.depends("booking_id", "amount_total", "invoice_ids.amount_residual")
    def _compute_rental_chain_amounts(self):
        for order in self:
            booking = order.booking_id
            if not booking:
                order.rental_chain_total = order.amount_total
                order.rental_chain_paid = 0.0
                order.rental_chain_residual = order.amount_total
                continue
            order.rental_chain_total = booking.chain_amount_total
            order.rental_chain_paid = booking.chain_amount_paid
            order.rental_chain_residual = booking.chain_amount_residual

    def action_view_booking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Booking"),
            "res_model": "primate.booking",
            "res_id": self.booking_id.id,
            "view_mode": "form",
        }
