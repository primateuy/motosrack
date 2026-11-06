# -*- coding: utf-8 -*-
{
    "name": "Motos Rack Pipa - Rental",
    "summary": "Motorbike rental on top of the generic booking agenda",
    "description": """
Motos Rack Pipa
===============

Motorbike rental for Praia da Pipa (RN, Brazil), built as a vertical on top
of ``primate_resource_booking``.

The operator marks a range on the agenda and everything else follows: the
sale order with the tier price, the confirmation that holds the motorbike,
the invoice and the payment, or the balance left to collect.

Each ``fleet.vehicle`` gets its own ``resource.resource`` so that the generic
agenda can book it. Rental prices come from native pricelists with
``min_quantity`` tiers over a single service product, so the rate of a tier
applies to every day of the rental.
""",
    "version": "19.0.1.0.0",
    "category": "Services",
    "author": "Primate",
    "website": "https://primate.uy",
    "license": "LGPL-3",
    "depends": [
        "primate_resource_booking",
        "sale_management",
        "account",
        "stock",
        "fleet",
        "l10n_br",
    ],
    "data": [
        "security/motosrack_security.xml",
        "security/ir.model.access.csv",
        "data/product_data.xml",
        "data/pricelist_data.xml",
        "data/account_journal_data.xml",
        "data/stock_data.xml",
        "data/block_reason_data.xml",
        "data/fleet_data.xml",
        "data/ir_config_parameter_data.xml",
        "data/ir_cron_data.xml",
        "wizards/booking_payment_views.xml",
        "wizards/booking_extend_views.xml",
        "wizards/booking_cancel_views.xml",
        "wizards/booking_deliver_views.xml",
        "wizards/booking_return_views.xml",
        "views/booking_views.xml",
        "views/sale_order_views.xml",
        "views/fleet_vehicle_views.xml",
        "views/res_config_settings_views.xml",
        "views/menus.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
}
