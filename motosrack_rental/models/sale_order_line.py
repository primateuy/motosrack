# -*- coding: utf-8 -*-

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    """Lets a line keep a price that no recomputation may overwrite."""

    _inherit = "sale.order.line"

    booking_id = fields.Many2one(
        comodel_name="primate.booking",
        string="Booking",
        copy=False,
        index="btree_not_null",
        ondelete="set null",
    )
    price_manual = fields.Boolean(
        string="Imposed Price",
        copy=False,
        help="The price was set by the rental logic or by hand. Odoo must "
             "not recompute it from the pricelist.",
    )

    @api.depends("price_manual")
    def _compute_price_unit(self):
        """Leave the imposed prices alone.

        The rental price depends on things the pricelist knows nothing about:
        the extension criterion in play, the days already invoiced in the
        chain, or simply the operator deciding the number. Recomputing those
        lines from the pricelist would quietly undo the decision.
        """
        manual = self.filtered("price_manual")
        super(SaleOrderLine, self - manual)._compute_price_unit()
        for line in manual:
            line.price_unit = line.price_unit
