# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)

# stock.location.name is not a translatable field, so the generic names of
# the vertical would stay in English for an operator working in Spanish.
# The shop names them in its own words, leaving alone any name that was
# already changed by hand.
HELMET_LOCATIONS = [
    ("primate_vehicle_rental.location_helmets_rented",
     "Rented helmets", "Cascos en alquiler"),
    ("primate_vehicle_rental.location_helmets_lost",
     "Lost or damaged helmets", "Cascos perdidos o dañados"),
]

# Payment methods the shop actually uses, as journals so that registering a
# payment reconciles the invoice exactly the way Odoo does natively.
JOURNALS = [
    ("journal_pix", "Pix", "PIX", "bank", 11),
    ("journal_cash", "Efectivo", "EFE", "cash", 12),
    ("journal_card", "Tarjeta", "TAR", "bank", 13),
]


def post_init_hook(env):
    """Adopt payment journals that could not be created from XML.

    The XML records fail when the database already has a journal using one
    of their codes. Here they can be matched by code and adopted instead.
    The helmet locations of the vertical are renamed here too.

    This hook cannot help with the chart of accounts, which is applied after
    every post-init hook has run -- see ``models/account_chart_template.py``.
    """
    _name_helmet_locations(env)
    _ensure_payment_journals(env)


def _name_helmet_locations(env):
    for xml_id, generic_name, shop_name in HELMET_LOCATIONS:
        location = env.ref(xml_id, raise_if_not_found=False)
        if location and location.name == generic_name:
            location.name = shop_name


def _ensure_payment_journals(env):
    Journal = env["account.journal"]
    company = env.company
    to_register = []
    for xml_suffix, name, code, journal_type, sequence in JOURNALS:
        xml_id = "motosrack.%s" % xml_suffix
        if env.ref(xml_id, raise_if_not_found=False):
            continue
        journal = Journal.search(
            [("code", "=", code), ("company_id", "=", company.id)], limit=1
        )
        if not journal:
            journal = Journal.create(
                {
                    "name": name,
                    "code": code,
                    "type": journal_type,
                    "sequence": sequence,
                    "company_id": company.id,
                }
            )
        to_register.append(
            {"xml_id": xml_id, "record": journal, "noupdate": True}
        )
    if to_register:
        env["ir.model.data"]._update_xmlids(to_register)
        _logger.info("Registered %s payment journal(s).", len(to_register))
