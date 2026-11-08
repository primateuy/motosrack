# -*- coding: utf-8 -*-

from odoo import models
from odoo.addons.account.models.chart_template import template


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @template("br", "account.journal")
    def _get_br_motosrack_account_journal(self):
        """Add the shop's payment methods to the Brazilian chart of accounts.

        The journals are also created from ``data/account_journal_data.xml``,
        which is what happens on a database that already has its chart of
        accounts. On a brand new database the order is the opposite: every
        module is installed first and the chart is only applied afterwards,
        from ``ir.module.module._register_hook``, and applying a chart wipes
        the journals that were there before it (``_load`` unlinks every
        ``TEMPLATE_MODELS`` record of the company). Declaring them here means
        the chart itself recreates them, under the very same XML ids, so both
        orders end up with the same three journals.
        """
        return {
            "motosrack.journal_pix": {
                "name": "Pix",
                "code": "PIX",
                "type": "bank",
                "sequence": 11,
            },
            "motosrack.journal_cash": {
                "name": "Efectivo",
                "code": "EFE",
                "type": "cash",
                "sequence": 12,
            },
            "motosrack.journal_card": {
                "name": "Tarjeta",
                "code": "TAR",
                "type": "bank",
                "sequence": 13,
            },
        }
