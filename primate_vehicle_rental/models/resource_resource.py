# -*- coding: utf-8 -*-

from odoo import fields, models


class ResourceResource(models.Model):
    """Link back from the booked resource to the vehicle behind it.

    Only so that the agenda can be told which resources are vehicles: without
    it the rows of the agenda would include every resource in the
    database, employees among them the day another vertical is installed.
    """

    _inherit = "resource.resource"

    vehicle_ids = fields.One2many(
        comodel_name="fleet.vehicle",
        inverse_name="resource_id",
        string="Vehicles",
    )
