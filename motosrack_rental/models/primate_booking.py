# -*- coding: utf-8 -*-

import math

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain

PAYMENT_STATES = [
    ("paid", "Paid in full"),
    ("deposit", "Deposit"),
    ("pending", "Pending"),
]

EXTENSION_CRITERIA = [
    ("recalculate", "A. Recalculate everything"),
    ("accumulated", "B. New days at the accumulated tier"),
    ("independent", "C. Independent"),
]


class PrimateBooking(models.Model):
    """Turns a generic booking into a motorbike rental.

    Everything the operator fills on the quick-create form lives here, and so
    does the one-transaction confirmation: validate availability, raise the
    sale order with the tier price, hold the bike, invoice it and collect.
    """

    _inherit = "primate.booking"

    # ------------------------------------------------------------------
    # The bike
    # ------------------------------------------------------------------

    # The bike is the field the operator picks; the resource is what the
    # generic agenda books. resource_id is required at database level, and an
    # inverse method runs after the INSERT, so the resource has to be
    # *precomputed* from the bike instead of inversed into it.
    vehicle_id = fields.Many2one(
        comodel_name="fleet.vehicle",
        string="Bike",
        index="btree_not_null",
        ondelete="restrict",
        help="The bike behind the booked resource.",
    )
    resource_id = fields.Many2one(
        compute="_compute_resource_id",
        store=True,
        readonly=False,
        precompute=True,
    )

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        string="Pricelist",
        compute="_compute_pricelist_id",
        store=True,
        readonly=False,
        help="Proposed from the customer, falling back to the default list.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        string="Currency",
        compute="_compute_currency_id",
        store=True,
    )
    rental_days = fields.Integer(
        string="Days",
        compute="_compute_rental_days",
        store=True,
        help="ceil((end - start - tolerance) / 24h), at least 1.",
    )
    manual_price = fields.Boolean(
        string="Manual Price",
        copy=False,
        help="Stops the price from being recalculated when the dates or the "
             "bike change. Use 'Recompute price' to go back to the tier.",
    )
    daily_price = fields.Monetary(
        string="Daily Price",
        compute="_compute_daily_price",
        store=True,
        readonly=False,
        currency_field="currency_id",
    )
    amount_rental = fields.Monetary(
        string="Rental Total",
        compute="_compute_amount_rental",
        store=True,
        currency_field="currency_id",
    )
    helmet_qty = fields.Integer(
        string="Helmets",
        compute="_compute_helmet_qty",
        store=True,
        readonly=False,
    )

    # ------------------------------------------------------------------
    # Billing
    # ------------------------------------------------------------------

    payment_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Payment Method",
        domain="[('type', 'in', ('bank', 'cash'))]",
        copy=False,
    )
    payment_state = fields.Selection(
        selection=PAYMENT_STATES,
        string="Payment Status",
        default="pending",
        copy=False,
    )
    deposit_amount = fields.Monetary(
        string="Deposit Amount",
        currency_field="currency_id",
        copy=False,
    )
    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        string="Order",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    invoice_ids = fields.Many2many(
        comodel_name="account.move",
        string="Invoices",
        compute="_compute_invoice_ids",
    )
    amount_total = fields.Monetary(
        string="Contracted Total",
        compute="_compute_amounts",
        currency_field="currency_id",
    )
    amount_paid = fields.Monetary(
        string="Collected Total",
        compute="_compute_amounts",
        currency_field="currency_id",
    )
    amount_residual = fields.Monetary(
        string="Balance",
        compute="_compute_amounts",
        currency_field="currency_id",
    )
    chain_amount_total = fields.Monetary(
        string="Contracted Total (chain)",
        compute="_compute_chain_amounts",
        currency_field="currency_id",
    )
    chain_amount_paid = fields.Monetary(
        string="Collected Total (chain)",
        compute="_compute_chain_amounts",
        currency_field="currency_id",
    )
    chain_amount_residual = fields.Monetary(
        string="Balance (chain)",
        compute="_compute_chain_amounts",
        currency_field="currency_id",
    )

    # ------------------------------------------------------------------
    # Extension chain
    # ------------------------------------------------------------------

    parent_booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Extension of",
        copy=False,
        ondelete="set null",
        index="btree_not_null",
    )
    child_booking_ids = fields.One2many(
        comodel_name="primate.booking",
        inverse_name="parent_booking_id",
        string="Extensions",
    )
    root_booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Original Booking",
        compute="_compute_root_booking_id",
        store=True,
        recursive=True,
        index="btree_not_null",
    )
    extension_criterion = fields.Selection(
        selection=EXTENSION_CRITERIA,
        string="Extension Criterion",
        copy=False,
    )
    is_extension = fields.Boolean(
        string="Is an Extension",
        compute="_compute_is_extension",
        store=True,
    )
    chain_days = fields.Integer(
        string="Accumulated Days",
        compute="_compute_chain_days",
        help="Days of the whole chain, which is what decides the tier of an "
             "extension.",
    )

    # ------------------------------------------------------------------
    # Delivery and return
    # ------------------------------------------------------------------

    delivery_datetime = fields.Datetime(
        string="Actual Delivery",
        copy=False,
        readonly=True,
    )
    return_datetime = fields.Datetime(
        string="Actual Return",
        copy=False,
        readonly=True,
    )
    helmets_delivered = fields.Integer(
        string="Helmets Delivered",
        copy=False,
        readonly=True,
    )
    helmets_returned = fields.Integer(
        string="Helmets Returned",
        copy=False,
        readonly=True,
    )
    helmets_pending = fields.Integer(
        string="Helmets Outstanding",
        compute="_compute_helmets_pending",
        store=True,
    )
    odometer_out = fields.Float(string="Mileage on Departure", copy=False, readonly=True)
    odometer_in = fields.Float(string="Mileage on Return", copy=False, readonly=True)
    fuel_out = fields.Selection(
        selection=[
            ("empty", "Empty"),
            ("quarter", "1/4"),
            ("half", "1/2"),
            ("three_quarters", "3/4"),
            ("full", "Full"),
        ],
        string="Fuel on Departure",
        copy=False,
        readonly=True,
    )
    fuel_in = fields.Selection(
        selection=[
            ("empty", "Empty"),
            ("quarter", "1/4"),
            ("half", "1/2"),
            ("three_quarters", "3/4"),
            ("full", "Full"),
        ],
        string="Fuel on Return",
        copy=False,
        readonly=True,
    )
    delivery_note = fields.Text(string="Delivery Notes", copy=False)
    return_note = fields.Text(string="Return Notes", copy=False)
    review_block_id = fields.Many2one(
        comodel_name="primate.booking.block",
        string="Review Block",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    late_hours = fields.Float(
        string="Hours Late",
        compute="_compute_late_hours",
        help="Hours between the planned end and the real return, net of the "
             "configured tolerance.",
    )

    # ==================================================================
    # Computes
    # ==================================================================

    @api.depends("vehicle_id")
    def _compute_resource_id(self):
        for booking in self:
            if booking.vehicle_id:
                booking.resource_id = booking.vehicle_id.resource_id
            else:
                # Bookings created straight on a resource (the generic
                # agenda, another vertical) keep the one they were given.
                booking.resource_id = booking.resource_id

    @api.depends("partner_id")
    def _compute_pricelist_id(self):
        default = self.env["motosrack.rental.parameters"]._default_pricelist()
        for booking in self:
            if booking.pricelist_id and not booking.partner_id:
                continue
            booking.pricelist_id = booking.partner_id.property_product_pricelist or default

    @api.depends("pricelist_id", "company_id")
    def _compute_currency_id(self):
        for booking in self:
            booking.currency_id = (
                booking.pricelist_id.currency_id or booking.company_id.currency_id
            )

    @api.depends("start", "stop")
    def _compute_rental_days(self):
        for booking in self:
            booking.rental_days = self._rental_days_for(booking.start, booking.stop)

    @api.depends("rental_days", "pricelist_id", "manual_price")
    def _compute_daily_price(self):
        for booking in self:
            if booking.manual_price:
                # Leave what the operator typed. The field is stored and
                # computed, so it still has to be assigned explicitly.
                booking.daily_price = booking.daily_price or 0.0
                continue
            booking.daily_price = booking._tier_daily_price(
                booking.pricelist_id, booking.rental_days
            )

    @api.depends("rental_days", "daily_price")
    def _compute_amount_rental(self):
        for booking in self:
            booking.amount_rental = booking.rental_days * booking.daily_price

    @api.depends("resource_id")
    def _compute_helmet_qty(self):
        default = self.env["motosrack.rental.parameters"]._param_int("default_helmets")
        for booking in self:
            if not booking.helmet_qty:
                booking.helmet_qty = default

    @api.depends("sale_order_id")
    def _compute_invoice_ids(self):
        for booking in self:
            booking.invoice_ids = booking.sale_order_id.invoice_ids

    @api.depends(
        "sale_order_id.amount_total",
        "sale_order_id.invoice_ids.payment_state",
        "sale_order_id.invoice_ids.amount_residual",
        "sale_order_id.invoice_ids.state",
    )
    def _compute_amounts(self):
        for booking in self:
            total, paid = booking._booking_amounts()
            booking.amount_total = total
            booking.amount_paid = paid
            booking.amount_residual = total - paid

    @api.depends(
        "root_booking_id",
        "sale_order_id.amount_total",
        "sale_order_id.invoice_ids.amount_residual",
        "sale_order_id.invoice_ids.state",
    )
    def _compute_chain_amounts(self):
        for booking in self:
            total = paid = 0.0
            for link in booking._chain_bookings():
                link_total, link_paid = link._booking_amounts()
                total += link_total
                paid += link_paid
            booking.chain_amount_total = total
            booking.chain_amount_paid = paid
            booking.chain_amount_residual = total - paid

    @api.depends("parent_booking_id", "parent_booking_id.root_booking_id")
    def _compute_root_booking_id(self):
        for booking in self:
            parent = booking.parent_booking_id
            booking.root_booking_id = (
                parent.root_booking_id or parent
            ) if parent else booking

    @api.depends("parent_booking_id")
    def _compute_is_extension(self):
        for booking in self:
            booking.is_extension = bool(booking.parent_booking_id)

    @api.depends("rental_days", "parent_booking_id")
    def _compute_chain_days(self):
        for booking in self:
            booking.chain_days = sum(booking._chain_bookings().mapped("rental_days"))

    @api.depends("helmets_delivered", "helmets_returned")
    def _compute_helmets_pending(self):
        for booking in self:
            booking.helmets_pending = max(
                0, booking.helmets_delivered - booking.helmets_returned
            )

    @api.depends("stop", "return_datetime")
    def _compute_late_hours(self):
        tolerance = self.env["motosrack.rental.parameters"]._param_float(
            "late_tolerance_hours"
        )
        for booking in self:
            reference = booking.return_datetime or fields.Datetime.now()
            if not booking.stop or booking.state not in ("in_use", "done"):
                booking.late_hours = 0.0
                continue
            delta = (reference - booking.stop).total_seconds() / 3600.0 - tolerance
            booking.late_hours = max(0.0, delta)

    # ==================================================================
    # Constraints
    # ==================================================================

    @api.constrains("helmet_qty")
    def _check_helmet_qty(self):
        maximum = self.env["motosrack.rental.parameters"]._param_int("max_helmets")
        for booking in self:
            if booking.helmet_qty < 0 or booking.helmet_qty > maximum:
                raise ValidationError(
                    _(
                        "The number of helmets must be between 0 and %(max)s.",
                        max=maximum,
                    )
                )

    # ==================================================================
    # Days and tier pricing
    # ==================================================================

    @api.model
    def _rental_days_for(self, start, stop):
        """Number of days charged for the span ``[start, stop)``.

        ``ceil((stop - start - tolerance) / 24h)``, never less than one. The
        tolerance is what lets a customer hand the bike back a couple of hours
        late without paying for a whole extra day.

        Args:
            start (datetime): start of the rental.
            stop (datetime): planned end of the rental.

        Returns:
            int: days to charge, at least 1.
        """
        if not start or not stop or stop <= start:
            return 1
        tolerance = self.env["motosrack.rental.parameters"]._param_float(
            "day_tolerance_hours"
        )
        hours = (stop - start).total_seconds() / 3600.0 - tolerance
        return max(1, int(math.ceil(hours / 24.0)))

    @api.model
    def _rental_product(self):
        product = self.env.ref(
            "motosrack_rental.product_rental_moto", raise_if_not_found=False
        )
        if not product:
            raise UserError(_("The rental product is missing. Reinstall the module."))
        return product.product_variant_id

    @api.model
    def _tier_quantity(self, days):
        """Day count used to look up the tier.

        Rentals longer than the longest tier are priced with that tier, which
        is what the parameter is for.
        """
        cap = self.env["motosrack.rental.parameters"]._param_int("max_tier_days")
        return min(days, cap) if cap else days

    @api.model
    def _tier_daily_price(self, pricelist, days):
        """Daily rate of the tier matching ``days`` on ``pricelist``.

        The quantity handed to the pricelist is the number of days, so the
        native ``min_quantity`` rules do the tiering: eight days on the
        General list are eight days at the 7-day rate, not a mix of rates.

        Args:
            pricelist (recordset): the pricelist to read, may be empty.
            days (int): days of the rental.

        Returns:
            float: the daily rate, 0.0 without a pricelist.
        """
        if not pricelist or days <= 0:
            return 0.0
        product = self._rental_product()
        return pricelist._get_product_price(
            product,
            self._tier_quantity(days),
            uom=product.uom_id,
            date=fields.Date.context_today(self),
        )

    @api.model
    def _tier_total(self, pricelist, days):
        """Total price of ``days`` days, honouring the optional tier cap.

        Tiers are not always monotonic: on the General list 29 days at the
        21-day rate cost R$2030 while 30 days cost R$1500. Strict tiers (the
        default) charge the 29 days as listed; with the cap enabled the
        rental never costs more than the total of a longer tier.
        """
        if days <= 0 or not pricelist:
            return 0.0
        total = days * self._tier_daily_price(pricelist, days)
        if not self.env["motosrack.rental.parameters"]._param_bool("tier_cap_enabled"):
            return total
        for threshold in self._tier_thresholds(pricelist):
            if threshold <= days:
                continue
            capped = threshold * self._tier_daily_price(pricelist, threshold)
            total = min(total, capped)
        return total

    @api.model
    def _tier_thresholds(self, pricelist):
        """Sorted ``min_quantity`` values of the rental tiers of ``pricelist``."""
        product = self._rental_product()
        items = self.env["product.pricelist.item"].search(
            [
                ("pricelist_id", "=", pricelist.id),
                "|",
                ("product_tmpl_id", "=", product.product_tmpl_id.id),
                ("product_id", "=", product.id),
            ]
        )
        return sorted({int(item.min_quantity) for item in items if item.min_quantity})

    def action_recompute_price(self):
        """Drop the manual price and go back to the tier."""
        self.write({"manual_price": False})
        for booking in self:
            booking.daily_price = booking._tier_daily_price(
                booking.pricelist_id, booking.rental_days
            )
            if booking.sale_order_id:
                booking._sync_order_line()
        return True

    # ==================================================================
    # Chain helpers
    # ==================================================================

    def _chain_bookings(self):
        """Every booking of the extension chain, the root included."""
        self.ensure_one()
        root = self.root_booking_id or self
        return self.search([("root_booking_id", "=", root.id)], order="start asc")

    def _booking_amounts(self):
        """Total contracted and total collected for this booking alone.

        Returns:
            tuple: ``(amount_total, amount_paid)``.
        """
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return 0.0, 0.0
        invoices = order.invoice_ids.filtered(lambda m: m.state == "posted")
        total = order.amount_total
        if invoices:
            # What is actually collected is what the posted invoices no
            # longer owe. Credit notes count with their own sign.
            paid = sum(
                (move.amount_total - move.amount_residual)
                * (-1 if move.move_type == "out_refund" else 1)
                for move in invoices
            )
        else:
            paid = 0.0
        return total, paid

    # ==================================================================
    # Confirmation: order, invoice and payment in one go
    # ==================================================================

    def action_confirm(self):
        """Hold the bike and raise everything the rental needs.

        In one transaction: validate availability listing the reasons on a
        conflict, create and confirm the sale order with the tier price, hold
        the bike, post the invoice for the total, and register the payment in
        the chosen journal when there is one to register.

        Bookings that are not rentals -- a resource that is not a bike of the
        fleet, which is what another vertical on the same agenda looks like
        -- keep the plain generic behaviour.
        """
        rentals = self.filtered("vehicle_id")
        others = self - rentals
        if others:
            super(PrimateBooking, others).action_confirm()
        for booking in rentals:
            booking._check_rental_ready()
            booking._check_availability()
            order = booking._ensure_sale_order()
            if order.state in ("draft", "sent"):
                order.action_confirm()
            super(PrimateBooking, booking).action_confirm()
            invoice = booking._create_and_post_invoice()
            booking._register_initial_payment(invoice)
            booking._post_confirmation_message()
        return True

    def _check_rental_ready(self):
        """Refuse to confirm a booking that is missing something essential."""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("The booking needs a customer before it can be confirmed."))
        if not self.pricelist_id:
            raise UserError(_("The booking needs a pricelist."))
        if self.payment_state == "deposit" and self.deposit_amount <= 0:
            raise UserError(_("A deposit needs an amount greater than zero."))
        if self.payment_state in ("paid", "deposit") and not self.payment_journal_id:
            raise UserError(
                _("Choose how the customer is paying before confirming.")
            )

    def _order_line_name(self):
        """Description of the rental line, naming the bike and the dates."""
        self.ensure_one()
        return _(
            "Rental %(moto)s from %(start)s to %(stop)s",
            moto=self.vehicle_id.rental_label or self.vehicle_id.name,
            start=self._format_datetime(self.start),
            stop=self._format_datetime(self.stop),
        )

    def _prepare_order_line_values(self):
        self.ensure_one()
        product = self._rental_product()
        return {
            "product_id": product.id,
            "name": self._order_line_name(),
            "product_uom_qty": self.rental_days,
            "product_uom_id": product.uom_id.id,
            "price_unit": self.daily_price,
            # The price comes from the tier (or from the operator), never
            # from a recomputation that does not know about the extension
            # criterion in play.
            "price_manual": True,
            "booking_id": self.id,
        }

    def _prepare_sale_order_values(self):
        self.ensure_one()
        return {
            "partner_id": self.partner_id.id,
            "pricelist_id": self.pricelist_id.id,
            "currency_id": self.currency_id.id,
            "company_id": self.company_id.id,
            "booking_id": self.id,
            "rental_parent_id": (
                self.parent_booking_id.sale_order_id.id
                if self.parent_booking_id
                else False
            ),
            "date_order": fields.Datetime.now(),
            "order_line": [Command.create(self._prepare_order_line_values())],
        }

    def _ensure_sale_order(self):
        """Return this booking's sale order, creating it the first time."""
        self.ensure_one()
        if self.sale_order_id:
            self._sync_order_line()
            return self.sale_order_id
        order = self.env["sale.order"].create(self._prepare_sale_order_values())
        self.sale_order_id = order
        return order

    def _rental_order_line(self):
        """The rental line of this booking's order, if there is one."""
        self.ensure_one()
        product = self._rental_product()
        return self.sale_order_id.order_line.filtered(
            lambda line: line.booking_id == self and line.product_id == product
        )[:1]

    def _sync_order_line(self):
        """Push the booking's dates, days and price back onto the order line.

        Only while the order has not been invoiced: a posted document is never
        edited, the difference is settled with a credit note or an extra
        invoice instead.
        """
        self.ensure_one()
        line = self._rental_order_line()
        if not line:
            return False
        if line.qty_invoiced:
            return False
        line.write(
            {
                "name": self._order_line_name(),
                "product_uom_qty": self.rental_days,
                "price_unit": self.daily_price,
                "price_manual": True,
            }
        )
        return True

    # ------------------------------------------------------------------
    # Invoicing
    # ------------------------------------------------------------------

    def _create_and_post_invoice(self):
        """Invoice what is not invoiced yet on this booking's order.

        Returns:
            recordset: the posted ``account.move``, empty when there was
                nothing left to invoice.
        """
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return self.env["account.move"]
        invoiceable = order.order_line.filtered(
            lambda line: line.product_uom_qty > line.qty_invoiced
        )
        if not invoiceable:
            return self.env["account.move"]
        invoice = order._create_invoices()
        invoice.action_post()
        return invoice

    def _register_initial_payment(self, invoice):
        """Collect what the operator said was collected.

        Nothing to collect (a pending booking) leaves the invoice open on
        purpose: the balance is then visible on the booking and collectable
        later with "Register Payment".
        """
        self.ensure_one()
        if not invoice or self.payment_state == "pending":
            return False
        amount = (
            invoice.amount_total
            if self.payment_state == "paid"
            else min(self.deposit_amount, invoice.amount_total)
        )
        if amount <= 0:
            return False
        return self._register_payment(invoice, amount, self.payment_journal_id)

    def _register_payment(self, invoice, amount, journal, payment_date=None):
        """Register ``amount`` against ``invoice`` and reconcile it.

        Goes through the native register-payment wizard so the payment is
        built, posted and matched exactly the way Odoo does it, including a
        partial payment leaving the rest open.

        Args:
            invoice (recordset): the posted customer invoice.
            amount (float): amount collected.
            journal (recordset): the journal standing for the payment method.
            payment_date (date): defaults to today.

        Returns:
            recordset: the created ``account.payment``.
        """
        self.ensure_one()
        if not journal:
            raise UserError(_("Choose a payment method before registering a payment."))
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "journal_id": journal.id,
                    "amount": amount,
                    "payment_date": payment_date or fields.Date.context_today(self),
                    "communication": invoice.name,
                    # A partial payment leaves the rest due instead of
                    # writing it off.
                    "payment_difference_handling": "open",
                }
            )
        )
        return wizard._create_payments()

    def action_view_sale_order(self):
        """Open the sale order raised by this booking."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Order"),
            "res_model": "sale.order",
            "res_id": self.sale_order_id.id,
            "view_mode": "form",
        }

    def action_register_payment(self):
        """Open the wizard that collects an outstanding balance."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Register Payment"),
            "res_model": "motosrack.booking.payment",
            "view_mode": "form",
            "target": "new",
            "context": {"default_booking_id": self.id},
        }

    def _open_invoices(self):
        """Posted invoices of the chain that still owe something."""
        self.ensure_one()
        return (
            self._chain_bookings()
            .mapped("sale_order_id.invoice_ids")
            .filtered(
                lambda move: move.state == "posted"
                and move.move_type == "out_invoice"
                and move.payment_state not in ("paid", "reversed")
            )
            .sorted("invoice_date")
        )

    def _post_confirmation_message(self):
        """Leave the money story of the confirmation in the chatter."""
        self.ensure_one()
        self.invalidate_recordset(["amount_total", "amount_paid", "amount_residual"])
        self.message_post(
            body=_(
                "Booking confirmed. Contracted total: %(total)s. "
                "Collected: %(paid)s. Balance: %(residual)s.",
                total=self._format_amount(self.amount_total),
                paid=self._format_amount(self.amount_paid),
                residual=self._format_amount(self.amount_residual),
            )
        )

    def _format_amount(self, amount):
        self.ensure_one()
        currency = self.currency_id or self.company_id.currency_id
        return currency.format(amount) if currency else "%.2f" % amount

    # ==================================================================
    # Delivery and return
    # ==================================================================

    def action_open_deliver(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Deliver Bike"),
            "res_model": "motosrack.booking.deliver",
            "view_mode": "form",
            "target": "new",
            "context": {"default_booking_id": self.id},
        }

    def action_open_return(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Return Bike"),
            "res_model": "motosrack.booking.return",
            "view_mode": "form",
            "target": "new",
            "context": {"default_booking_id": self.id},
        }

    def _do_deliver(self, moment, helmets, note=False, odometer=0.0, fuel=False):
        """Record the real delivery of the bike and move the helmets out.

        Args:
            moment (datetime): when the bike actually left.
            helmets (int): helmets handed over.
            note (str): free text.
            odometer (float): mileage at departure.
            fuel (str): fuel level at departure.
        """
        self.ensure_one()
        if self.state != "confirmed":
            raise UserError(
                _("Only a confirmed booking can be delivered.")
            )
        self.write(
            {
                "delivery_datetime": moment,
                "helmets_delivered": helmets,
                "delivery_note": note,
                "odometer_out": odometer,
                "fuel_out": fuel,
            }
        )
        if odometer:
            self._log_odometer(odometer, moment)
        self._move_helmets(helmets, outgoing=True)
        self.action_start()
        self.message_post(
            body=_(
                "Bike delivered on %(moment)s with %(helmets)s helmet(s).",
                moment=self._format_datetime(moment),
                helmets=helmets,
            )
        )
        return True

    def _do_return(self, moment, helmets_back, helmets_lost=0, note=False,
                   odometer=0.0, fuel=False):
        """Record the real return, bring the helmets back and block the bike.

        A returned bike is not available again on its own: an open "pending
        review" block goes up from the moment it came back, and somebody has
        to press "Release bike" to close it.
        """
        self.ensure_one()
        if self.state != "in_use":
            raise UserError(_("Only a booking in use can be returned."))
        self.write(
            {
                "return_datetime": moment,
                "helmets_returned": helmets_back,
                "return_note": note,
                "odometer_in": odometer,
                "fuel_in": fuel,
            }
        )
        if odometer:
            self._log_odometer(odometer, moment)
        if helmets_back:
            self._move_helmets(helmets_back, outgoing=False)
        if helmets_lost:
            self._write_off_helmets(helmets_lost)
        self.action_done()
        self._open_review_block(moment)
        self._handle_late_return()
        self.message_post(
            body=_(
                "Bike returned on %(moment)s. Helmets returned: %(back)s. "
                "Helmets lost or damaged: %(lost)s.",
                moment=self._format_datetime(moment),
                back=helmets_back,
                lost=helmets_lost,
            )
        )
        return True

    def _log_odometer(self, value, moment):
        """Push a mileage reading into the fleet history."""
        self.ensure_one()
        if not self.vehicle_id:
            return False
        self.env["fleet.vehicle.odometer"].create(
            {
                "vehicle_id": self.vehicle_id.id,
                "value": value,
                "date": fields.Date.to_date(moment),
            }
        )
        # fleet.vehicle.odometer is computed without @api.depends, so the
        # value stays cached and does not reflect a record created in the
        # same transaction. It has to be invalidated by hand.
        self.vehicle_id.invalidate_recordset(["odometer"])
        return True

    def _open_review_block(self, moment):
        """Block the bike from ``moment`` until somebody releases it."""
        self.ensure_one()
        if self.review_block_id:
            return self.review_block_id
        reason = self.env.ref(
            "primate_resource_booking.block_reason_review", raise_if_not_found=False
        )
        if not reason or not self.resource_id:
            return self.env["primate.booking.block"]
        block = self.env["primate.booking.block"].create(
            {
                "resource_id": self.resource_id.id,
                "reason_id": reason.id,
                "start": moment,
                "stop": False,
                "note": _("Review after booking %s", self.display_name),
            }
        )
        self.review_block_id = block
        return block

    def action_release_vehicle(self):
        """Close the review block: the bike is ready to go out again."""
        for booking in self:
            if not booking.review_block_id:
                raise UserError(_("This booking has no review block to close."))
            booking.review_block_id.action_close()
            booking.message_post(body=_("Bike released: the review block is closed."))
        return True

    # ------------------------------------------------------------------
    # Helmets as real stock
    # ------------------------------------------------------------------

    @api.model
    def _helmet_product(self):
        product = self.env.ref(
            "motosrack_rental.product_helmet", raise_if_not_found=False
        )
        return product.product_variant_id if product else False

    @api.model
    def _helmet_locations(self):
        """Return ``(stock, rented, lost)`` locations for the helmets."""
        ref = self.env.ref
        return (
            ref("stock.stock_location_stock", raise_if_not_found=False),
            ref("motosrack_rental.location_helmets_rented", raise_if_not_found=False),
            ref("motosrack_rental.location_helmets_lost", raise_if_not_found=False),
        )

    def _move_helmets(self, quantity, outgoing=True):
        """Move ``quantity`` helmets between stock and the rented location.

        Helmets out with a customer are still ours, so they only move to
        another internal location instead of leaving the company.
        """
        self.ensure_one()
        product = self._helmet_product()
        stock, rented, _lost = self._helmet_locations()
        if not product or not stock or not rented or quantity <= 0:
            return self.env["stock.move"]
        source, destination = (stock, rented) if outgoing else (rented, stock)
        return self._create_helmet_move(
            product,
            quantity,
            source,
            destination,
            _("Helmet delivery %s") % self.display_name
            if outgoing
            else _("Helmet return %s") % self.display_name,
        )

    def _write_off_helmets(self, quantity):
        """Send the helmets that never came back to the loss location.

        They must not land back in available stock: the shortage has to show
        up in the counts and in the valuation.
        """
        self.ensure_one()
        product = self._helmet_product()
        _stock, rented, lost = self._helmet_locations()
        if not product or not rented or not lost or quantity <= 0:
            return self.env["stock.move"]
        return self._create_helmet_move(
            product,
            quantity,
            rented,
            lost,
            _("Helmets lost or damaged %s") % self.display_name,
        )

    def _create_helmet_move(self, product, quantity, source, destination, name):
        """Create and validate one helmet stock move."""
        self.ensure_one()
        # stock.move has no 'name' in 19.0: the label of a move is
        # description_picking, and 'reference' is computed.
        move = self.env["stock.move"].create(
            {
                "description_picking": name,
                "product_id": product.id,
                "product_uom_qty": quantity,
                "product_uom": product.uom_id.id,
                "location_id": source.id,
                "location_dest_id": destination.id,
                "company_id": self.company_id.id,
                "origin": self.display_name,
            }
        )
        move._action_confirm()
        move._action_assign()
        move.quantity = quantity
        move.picked = True
        move._action_done()
        return move

    # ------------------------------------------------------------------
    # Late returns
    # ------------------------------------------------------------------

    def _handle_late_return(self):
        """Suggest a surcharge and warn about the next booking of the bike."""
        self.ensure_one()
        self.invalidate_recordset(["late_hours"])
        if self.late_hours <= 0:
            return False
        extra_days = max(1, int(math.ceil(self.late_hours / 24.0)))
        self._add_late_fee_line(extra_days)
        self._warn_next_booking()
        return True

    def _add_late_fee_line(self, extra_days):
        """Add the suggested surcharge as its own order line.

        A suggestion, not a verdict: the line is an ordinary order line the
        operator can edit or delete before invoicing it.
        """
        self.ensure_one()
        order = self.sale_order_id
        product = self.env.ref(
            "motosrack_rental.product_late_fee", raise_if_not_found=False
        )
        if not order or not product or order.state not in ("sale", "done"):
            return False
        variant = product.product_variant_id
        existing = order.order_line.filtered(
            lambda line: line.product_id == variant and line.booking_id == self
        )
        if existing:
            return False
        order.order_line = [
            Command.create(
                {
                    "product_id": variant.id,
                    "name": _(
                        "Late surcharge (%(days)s day(s)) - %(moto)s",
                        days=extra_days,
                        moto=self.vehicle_id.rental_label or self.vehicle_id.name,
                    ),
                    "product_uom_qty": extra_days,
                    "product_uom_id": variant.uom_id.id,
                    "price_unit": self.daily_price,
                    "price_manual": True,
                    "booking_id": self.id,
                }
            )
        ]
        self.message_post(
            body=_(
                "Returned late: a surcharge of "
                "%(days)s day(s) at %(rate)s per day was suggested. It can be edited or removed "
                "on the order before it is invoiced.",
                days=extra_days,
                rate=self._format_amount(self.daily_price),
            )
        )
        return True

    def _next_booking(self):
        """The next booking holding this bike after this one."""
        self.ensure_one()
        if not self.resource_id:
            return self.browse()
        return self.search(
            [
                ("resource_id", "=", self.resource_id.id),
                ("state", "in", ("confirmed", "in_use")),
                ("start", ">=", self.stop),
                ("id", "!=", self.id),
            ],
            order="start asc",
            limit=1,
        )

    def _warn_next_booking(self):
        """Warn when the delay eats into the next booking of the bike."""
        self.ensure_one()
        reference = self.return_datetime or fields.Datetime.now()
        following = self._next_booking()
        if not following or following.start >= reference:
            return False
        message = _(
            "The delay compromises booking %(booking)s, which starts on "
            "%(start)s.",
            booking=following.display_name,
            start=self._format_datetime(following.start),
        )
        self.message_post(body=message)
        following.message_post(body=_(
            "The previous booking %(booking)s came back on %(moment)s, "
            "after this one was due to start.",
            booking=self.display_name,
            moment=self._format_datetime(reference),
        ))
        following.activity_schedule(
            "mail.mail_activity_data_warning",
            note=message,
            user_id=self.env.user.id,
        )
        return True

    @api.model
    def _cron_check_overdue_bookings(self):
        """Flag the bikes that are out late and are blocking a next booking.

        Runs daily. Only raises an activity once per booking: the activity
        itself is the memory of having warned.
        """
        now = fields.Datetime.now()
        tolerance = self.env["motosrack.rental.parameters"]._param_float(
            "late_tolerance_hours"
        )
        overdue = self.search(
            [("state", "=", "in_use"), ("stop", "<", now)]
        ).filtered(lambda b: (now - b.stop).total_seconds() / 3600.0 > tolerance)
        for booking in overdue:
            following = booking._next_booking()
            if not following:
                continue
            if booking.activity_ids.filtered(
                lambda a: a.activity_type_id
                == self.env.ref("mail.mail_activity_data_warning")
            ):
                continue
            booking.activity_schedule(
                "mail.mail_activity_data_warning",
                note=_(
                    "The bike is still out and booking %(booking)s starts on "
                    "%(start)s.",
                    booking=following.display_name,
                    start=booking._format_datetime(following.start),
                ),
                user_id=booking.create_uid.id or self.env.uid,
            )
        return True

    # ==================================================================
    # Extensions
    # ==================================================================

    def action_open_extend(self):
        """Open the wizard that extends an ongoing or confirmed rental."""
        self.ensure_one()
        if self.state not in ("confirmed", "in_use"):
            raise UserError(
                _("Only a confirmed or ongoing booking can be extended.")
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("Extend Rental"),
            "res_model": "motosrack.booking.extend",
            "view_mode": "form",
            "target": "new",
            "context": {"default_booking_id": self.id},
        }

    def _extension_amount(self, new_stop, criterion):
        """Price of extending this booking until ``new_stop``.

        The three criteria all look at the *chain*, not at this booking
        alone, because what the customer is renting is one long rental split
        across several orders.

        * ``recalculate``: the whole chain repriced at the tier of the total,
          minus what the chain has already been invoiced.
        * ``accumulated`` (the default): only the new days, but charged at the
          tier the accumulated total reaches.
        * ``independent``: the new days priced on their own, as if it were a
          fresh rental.

        Args:
            new_stop (datetime): the new end of the rental.
            criterion (str): one of ``recalculate`` / ``accumulated`` /
                ``independent``.

        Returns:
            tuple: ``(new_days, amount, daily_price)``.
        """
        self.ensure_one()
        pricelist = self.pricelist_id
        new_days = self._rental_days_for(self.stop, new_stop)
        previous_days = sum(self._chain_bookings().mapped("rental_days"))
        total_days = previous_days + new_days

        if criterion == "independent":
            daily = self._tier_daily_price(pricelist, new_days)
            return new_days, self._tier_total(pricelist, new_days), daily

        if criterion == "accumulated":
            daily = self._tier_daily_price(pricelist, total_days)
            return new_days, new_days * daily, daily

        # recalculate: reprice everything and charge the difference.
        daily = self._tier_daily_price(pricelist, total_days)
        already_invoiced = sum(
            booking._booking_amounts()[0] for booking in self._chain_bookings()
        )
        amount = self._tier_total(pricelist, total_days) - already_invoiced
        return new_days, amount, daily

    def _create_extension(self, new_stop, criterion, payment_state="pending",
                          journal=None, deposit=0.0):
        """Extend the rental with a new contiguous booking and its own order.

        The bike never comes back in between: no delivery, no return, the
        customer simply keeps it. What is created is a booking starting
        exactly where this one ends, plus a sale order linked to the original
        one. Invoices already issued are never touched.

        Args:
            new_stop (datetime): new end of the rental.
            criterion (str): pricing criterion, see ``_extension_amount``.
            payment_state (str): how the extension is being paid.
            journal (recordset): payment journal, when something is collected.
            deposit (float): amount of the deposit, for ``deposit``.

        Returns:
            recordset: the new ``primate.booking``.
        """
        self.ensure_one()
        if new_stop <= self.stop:
            raise UserError(
                _("The new end has to be later than the current one.")
            )
        new_days, amount, daily = self._extension_amount(new_stop, criterion)

        # The bike has to be free over the new stretch. The check is a
        # warning on the chatter and a hard stop on a real conflict, so the
        # operator finds out before anything is invoiced.
        availability = self._get_availability(
            self.resource_id, self.stop, new_stop, exclude_bookings=self
        )
        if availability["bookings"]:
            raise UserError(
                _(
                    "Cannot extend: %(resource)s is already taken.\n"
                    "%(details)s",
                    resource=self.resource_id.name,
                    details="\n".join(
                        " - %s" % reason for reason in availability["reasons"]
                    ),
                )
            )
        extension = self.create(
            {
                "resource_id": self.resource_id.id,
                "partner_id": self.partner_id.id,
                "start": self.stop,
                "stop": new_stop,
                "pricelist_id": self.pricelist_id.id,
                "parent_booking_id": self.id,
                "extension_criterion": criterion,
                "helmet_qty": 0,
                "payment_state": payment_state,
                "payment_journal_id": journal.id if journal else False,
                "deposit_amount": deposit,
                "manual_price": True,
                # The amount of a criterion is not always days x daily rate:
                # A nets out what the chain was already invoiced. So the unit
                # price carried onto the order line is the one that lands on
                # the wanted total, and it is set before confirming, while
                # nothing has been invoiced yet.
                "daily_price": amount / new_days if new_days else amount,
                "note": _("Extension of %s", self.display_name),
            }
        )
        extension.action_confirm()
        if availability["blocks"]:
            extension.message_post(
                body=_(
                    "Careful: the extended span overlaps a block.\n%s",
                    "\n".join(" - %s" % r for r in availability["reasons"]),
                )
            )
        self.message_post(
            body=_(
                "Extended to %(stop)s by %(days)s day(s). Criterion: "
                "%(criterion)s. Amount: %(amount)s.",
                stop=self._format_datetime(new_stop),
                days=new_days,
                criterion=dict(EXTENSION_CRITERIA).get(criterion, criterion),
                amount=self._format_amount(amount),
            )
        )
        return extension

    # ==================================================================
    # Changes and cancellation
    # ==================================================================

    @api.model_create_multi
    def create(self, vals_list):
        """Keep the bike and the resource in step whichever one was given."""
        for vals in vals_list:
            if vals.get("resource_id") and not vals.get("vehicle_id"):
                vals["vehicle_id"] = self._vehicle_of_resource(vals["resource_id"])
        return super().create(vals_list)

    @api.model
    def _vehicle_of_resource(self, resource_id):
        vehicle = self.env["fleet.vehicle"].search(
            [("resource_id", "=", resource_id)], limit=1
        )
        return vehicle.id or False

    def write(self, vals):
        """Revalidate and reprice when the dates or the bike change.

        A change before delivery is a normal edit: availability is checked
        again and the price follows the tier, unless the operator took the
        price over by hand.
        """
        reprice = {"start", "stop", "resource_id", "vehicle_id", "pricelist_id"} & set(vals)
        if vals.get("resource_id") and "vehicle_id" not in vals:
            vals = dict(vals, vehicle_id=self._vehicle_of_resource(vals["resource_id"]))
        result = super().write(vals)
        if reprice:
            for booking in self:
                if booking.state in ("done", "cancelled") or booking.delivery_datetime:
                    continue
                if booking.sale_order_id:
                    booking._sync_order_line()
                    booking._warn_about_invoiced_difference()
        return result

    def _warn_about_invoiced_difference(self):
        """Say out loud when a change no longer fits the invoice already issued.

        Posted documents are never edited: the difference is settled with a
        credit note or an extra invoice, and that decision stays with a human.
        """
        self.ensure_one()
        invoiced = self.sale_order_id.invoice_ids.filtered(
            lambda move: move.state == "posted"
        )
        if not invoiced:
            return False
        invoiced_amount = sum(
            move.amount_untaxed * (-1 if move.move_type == "out_refund" else 1)
            for move in invoiced
        )
        # The order itself cannot be used as the reference: its rental line
        # is frozen as soon as it is invoiced, so its total never moves and
        # the difference would always be zero. What the rental is worth after
        # the change is the booking's own amount plus whatever else the order
        # carries (a late surcharge, for instance).
        other_lines = self.sale_order_id.order_line - self._rental_order_line()
        expected = self.amount_rental + sum(other_lines.mapped("price_subtotal"))
        difference = expected - invoiced_amount
        if self.currency_id.is_zero(difference):
            return False
        if difference > 0:
            body = _(
                "The change leaves %(amount)s uninvoiced. A complementary invoice has to be issued: "
                "posted invoices are never touched.",
                amount=self._format_amount(difference),
            )
        else:
            body = _(
                "The change leaves %(amount)s over-invoiced. A credit note has to be issued: "
                "posted invoices are never touched.",
                amount=self._format_amount(abs(difference)),
            )
        self.message_post(body=body)
        return True

    def action_cancel(self):
        """Free the bike and ask what happens with what was collected."""
        for booking in self:
            if booking.state == "in_use":
                raise UserError(
                    _("Return the bike before cancelling an ongoing rental.")
                )
        bookings_with_money = self.filtered(lambda b: b.amount_paid > 0)
        result = super().action_cancel()
        for booking in self:
            if booking.sale_order_id and booking.sale_order_id.state != "cancel":
                # The order follows the booking, but a posted invoice does
                # not: that is what the refund wizard is for.
                booking.sale_order_id.with_context(
                    disable_cancel_warning=True
                )._action_cancel()
        if len(bookings_with_money) == 1:
            return bookings_with_money.action_open_cancel_wizard()
        return result

    def action_open_cancel_wizard(self):
        """Open the wizard deciding what to do with what was collected."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cancellation: what to do with what was collected"),
            "res_model": "motosrack.booking.cancel",
            "view_mode": "form",
            "target": "new",
            "context": {"default_booking_id": self.id},
        }
