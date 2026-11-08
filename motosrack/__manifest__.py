# -*- coding: utf-8 -*-
{
    "name": "Motos Rack Pipa",
    "summary": "Motos Rack Pipa: fleet, pricelists and payment methods",
    "description": """
Motos Rack Pipa
===============

What belongs to this shop and to no other: the eight Honda Pop, the
General and Moradores pricelists with their tiers, and the three journals
the shop gets paid through (Pix, cash and card).

The rental itself lives in ``primate_vehicle_rental``, which knows nothing
about Pipa and can be installed for any other rental business.
""",
    "version": "19.0.1.0.0",
    "category": "Services",
    "author": "Primate",
    "website": "https://primate.uy",
    "license": "LGPL-3",
    "depends": [
        "primate_vehicle_rental",
        "l10n_br",
    ],
    "data": [
        "data/account_journal_data.xml",
        "data/pricelist_data.xml",
        "data/fleet_data.xml",
        "data/ir_config_parameter_data.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
}
