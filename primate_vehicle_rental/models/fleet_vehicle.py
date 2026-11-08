# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class FleetVehicle(models.Model):
    """Gives every vehicle the ``resource.resource`` the agenda books.

    The agenda knows nothing about vehicles: it books resources. Rather than
    teaching it about fleet, each vehicle carries its own resource and the two
    names are kept in sync.
    """

    _inherit = "fleet.vehicle"

    # fleet.vehicle.name is computed as "Brand/Model/Plate" and falls back to
    # "No Plate", which would show the eight vehicles as eight identical rows on
    # the agenda. The shop calls them "Moto 1".."Moto 8", so they get a label
    # of their own that does not depend on having a plate.
    rental_label = fields.Char(
        string="Rental Name",
        compute="_compute_rental_label",
        store=True,
        readonly=False,
        help="Name used on the booking agenda. Defaults to the fleet name.",
    )
    resource_id = fields.Many2one(
        comodel_name="resource.resource",
        string="Resource",
        ondelete="restrict",
        copy=False,
        readonly=True,
        help="Technical: what the booking agenda actually books.",
    )
    booking_ids = fields.One2many(
        comodel_name="primate.booking",
        inverse_name="vehicle_id",
        string="Bookings",
    )
    booking_count = fields.Integer(
        string="Bookings Count",
        compute="_compute_booking_count",
    )
    is_available_now = fields.Boolean(
        string="Available Now",
        related="resource_id.is_available_now",
    )
    unavailability_reason = fields.Char(
        string="Unavailability Reason",
        related="resource_id.unavailability_reason",
    )

    @api.depends("name")
    def _compute_rental_label(self):
        for vehicle in self:
            if not vehicle.rental_label:
                vehicle.rental_label = vehicle.name

    def _compute_booking_count(self):
        counts = {
            vehicle.id: count
            for vehicle, count in self.env["primate.booking"]._read_group(
                [("vehicle_id", "in", self.ids)],
                groupby=["vehicle_id"],
                aggregates=["__count"],
            )
        }
        for vehicle in self:
            vehicle.booking_count = counts.get(vehicle.id, 0)

    # ------------------------------------------------------------------
    # Resource plumbing
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        vehicles = super().create(vals_list)
        vehicles._ensure_resource()
        return vehicles

    def write(self, vals):
        result = super().write(vals)
        if "rental_label" in vals or "name" in vals:
            for vehicle in self:
                if vehicle.resource_id and vehicle.resource_id.name != vehicle._resource_name():
                    vehicle.resource_id.name = vehicle._resource_name()
        if "active" in vals:
            # Archiving a vehicle must take it out of the agenda too, otherwise
            # it keeps showing up as a bookable row.
            for vehicle in self:
                if vehicle.resource_id and vehicle.resource_id.active != vehicle.active:
                    vehicle.resource_id.active = vehicle.active
        return result

    def _resource_name(self):
        self.ensure_one()
        return self.rental_label or self.name or _("Vehicle")

    def _ensure_resource(self):
        """Create the missing resources of these vehicles.

        Also used by the post-install hook so that vehicles that already
        existed before the module was installed join the agenda.
        """
        Resource = self.env["resource.resource"]
        for vehicle in self:
            if vehicle.resource_id:
                continue
            vehicle.resource_id = Resource.create(
                {
                    "name": vehicle._resource_name(),
                    "resource_type": "material",
                    "company_id": vehicle.company_id.id or self.env.company.id,
                    "tz": vehicle.company_id.partner_id.tz or self.env.user.tz or "UTC",
                }
            )
        return True

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_view_bookings(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "primate_vehicle_rental.action_rental_booking"
        )
        action["domain"] = [("vehicle_id", "=", self.id)]
        action["context"] = {"default_vehicle_id": self.id}
        return action
