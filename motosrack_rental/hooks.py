# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)

# Payment methods the shop actually uses, as journals so that registering a
# payment reconciles the invoice exactly the way Odoo does natively.
JOURNALS = [
    ("journal_pix", "Pix", "PIX", "bank", 11),
    ("journal_cash", "Efectivo", "EFE", "cash", 12),
    ("journal_card", "Tarjeta", "TAR", "bank", 13),
]


def post_init_hook(env):
    """Finish the install once every other module has had its turn.

    Two things cannot be done from the data files:

    * Vehicles that already existed before the module was installed have no
      resource, so they would never show up on the agenda.
    * The three payment journals may be missing: the XML records fail to be
      created when the database already has a journal using one of their
      codes. Here they can be matched by code and simply adopted.

    This hook cannot help with the chart of accounts, which is applied after
    every post-init hook has run -- see ``account_chart_template.py``.
    """
    _ensure_vehicle_resources(env)
    _ensure_payment_journals(env)


def _ensure_vehicle_resources(env):
    vehicles = env["fleet.vehicle"].with_context(active_test=False).search(
        [("resource_id", "=", False)]
    )
    if vehicles:
        vehicles._ensure_resource()
        _logger.info("Created a booking resource for %s vehicle(s).", len(vehicles))


def _ensure_payment_journals(env):
    Journal = env["account.journal"]
    company = env.company
    to_register = []
    for xml_suffix, name, code, journal_type, sequence in JOURNALS:
        xml_id = "motosrack_rental.%s" % xml_suffix
        if env.ref(xml_id, raise_if_not_found=False):
            continue
        # A journal code is unique per company: reuse one that is already
        # there rather than failing on a second install.
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
