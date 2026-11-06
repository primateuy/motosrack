# -*- coding: utf-8 -*-

from odoo import api, fields, models

# Every business rule the shop may want to tune lives here, as a parameter,
# instead of being hardcoded somewhere in the pricing code.
PARAMS = {
    "day_tolerance_hours": ("motosrack_rental.day_tolerance_hours", "2.0"),
    "max_tier_days": ("motosrack_rental.max_tier_days", "30"),
    "tier_cap_enabled": ("motosrack_rental.tier_cap_enabled", "False"),
    "default_extension_criterion": (
        "motosrack_rental.default_extension_criterion",
        "accumulated",
    ),
    "late_tolerance_hours": ("motosrack_rental.late_tolerance_hours", "2.0"),
    "default_helmets": ("motosrack_rental.default_helmets", "2"),
    "max_helmets": ("motosrack_rental.max_helmets", "2"),
}


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    rental_day_tolerance_hours = fields.Float(
        string="Day Tolerance (hours)",
        config_parameter="motosrack_rental.day_tolerance_hours",
        default=2.0,
        help="Grace given before a started day is charged. Days are "
             "ceil((end - start - tolerance) / 24h), never less than one.",
    )
    rental_max_tier_days = fields.Integer(
        string="Longest Tier (days)",
        config_parameter="motosrack_rental.max_tier_days",
        default=30,
        help="Rentals longer than this are priced with this tier. Raise it "
             "if a longer tier is added to the pricelists.",
    )
    rental_tier_cap_enabled = fields.Boolean(
        string="Cap at the Next Tier",
        config_parameter="motosrack_rental.tier_cap_enabled",
        default=False,
        help="Tiers are not always monotonic: 29 days can cost more than 30. "
             "Off (the default) the tiers are applied strictly. On, a rental "
             "never costs more than the total of the next tier.",
    )
    rental_default_extension_criterion = fields.Selection(
        selection=[
            ("recalculate", "A. Recalculate the whole chain"),
            ("accumulated", "B. New days at the accumulated tier"),
            ("independent", "C. Independent"),
        ],
        string="Default Extension Criterion",
        config_parameter="motosrack_rental.default_extension_criterion",
        default="accumulated",
    )
    rental_late_tolerance_hours = fields.Float(
        string="Late Return Tolerance (hours)",
        config_parameter="motosrack_rental.late_tolerance_hours",
        default=2.0,
        help="A return later than the planned end plus this tolerance "
             "suggests a surcharge.",
    )
    rental_default_helmets = fields.Integer(
        string="Helmets by Default",
        config_parameter="motosrack_rental.default_helmets",
        default=2,
    )
    rental_max_helmets = fields.Integer(
        string="Helmets at Most",
        config_parameter="motosrack_rental.max_helmets",
        default=2,
    )
    rental_default_pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        string="Default Pricelist",
        config_parameter="motosrack_rental.default_pricelist_id",
        help="Used when the customer has none of their own.",
    )


class RentalParameters(models.AbstractModel):
    """Reads the rental parameters, with the defaults in one single place."""

    _name = "motosrack.rental.parameters"
    _description = "Motos Rack Rental Parameters"

    @api.model
    def _param(self, key):
        """Return the raw value of a rental parameter.

        Args:
            key (str): short name, as used in ``PARAMS``.

        Returns:
            str: the stored value, or the default when it was never set.
        """
        full_key, default = PARAMS[key]
        return self.env["ir.config_parameter"].sudo().get_param(full_key, default)

    @api.model
    def _param_float(self, key):
        try:
            return float(self._param(key))
        except (TypeError, ValueError):
            return float(PARAMS[key][1])

    @api.model
    def _param_int(self, key):
        try:
            return int(float(self._param(key)))
        except (TypeError, ValueError):
            return int(float(PARAMS[key][1]))

    @api.model
    def _param_bool(self, key):
        return str(self._param(key)).strip().lower() in ("1", "true", "yes")

    @api.model
    def _default_pricelist(self):
        """Pricelist proposed when the customer has none of their own."""
        raw = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("motosrack_rental.default_pricelist_id")
        )
        pricelist = self.env["product.pricelist"]
        if raw:
            pricelist = pricelist.browse(int(raw)).exists()
        if not pricelist:
            pricelist = self.env.ref(
                "motosrack_rental.pricelist_general", raise_if_not_found=False
            ) or self.env["product.pricelist"]
        return pricelist
