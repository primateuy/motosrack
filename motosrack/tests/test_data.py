# -*- coding: utf-8 -*-

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestMotosRackData(TransactionCase):
    """The shop's own data: fleet, tiers and payment methods."""

    def test_the_eight_bikes_are_bookable(self):
        """Every bike needs a resource or the agenda cannot hold it."""
        bikes = self.env["fleet.vehicle"].browse(
            [self.env.ref("motosrack.moto_%s" % number).id for number in range(1, 9)]
        )
        self.assertEqual(len(bikes), 8)
        self.assertTrue(all(bikes.mapped("resource_id")))
        self.assertEqual(len(set(bikes.mapped("resource_id").ids)), 8)

    def test_general_tiers(self):
        """The tiers of the General list, as the business priced them."""
        Booking = self.env["primate.booking"]
        general = self.env.ref("motosrack.pricelist_general")
        expected = {1: 130.0, 3: 130.0, 4: 120.0, 7: 100.0, 8: 100.0,
                    10: 90.0, 14: 80.0, 21: 70.0, 30: 50.0, 45: 50.0}
        for days, price in expected.items():
            self.assertEqual(
                Booking._tier_daily_price(general, days), price,
                "%s days should be priced at %s" % (days, price),
            )

    def test_resident_tiers(self):
        """The tiers of the Moradores list."""
        Booking = self.env["primate.booking"]
        moradores = self.env.ref("motosrack.pricelist_moradores")
        expected = {1: 80.0, 4: 75.0, 7: 70.0, 13: 70.0, 14: 60.0, 30: 40.0}
        for days, price in expected.items():
            self.assertEqual(Booking._tier_daily_price(moradores, days), price)

    def test_payment_journals_survive_the_chart_of_accounts(self):
        """The three journals have to exist after the chart is applied."""
        for xml_id, code in (
            ("motosrack.journal_pix", "PIX"),
            ("motosrack.journal_cash", "EFE"),
            ("motosrack.journal_card", "TAR"),
        ):
            journal = self.env.ref(xml_id, raise_if_not_found=False)
            self.assertTrue(journal, "%s is missing" % xml_id)
            self.assertEqual(journal.code, code)

    def test_default_pricelist_is_the_general_one(self):
        """A walk-in customer without a list of their own gets General."""
        default = self.env["primate.rental.parameters"]._default_pricelist()
        self.assertEqual(default, self.env.ref("motosrack.pricelist_general"))
