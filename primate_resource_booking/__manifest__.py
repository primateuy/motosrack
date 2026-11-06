# -*- coding: utf-8 -*-
{
    "name": "Primate Resource Booking",
    "summary": "Generic booking agenda over resources, with a timeline view",
    "description": """
Generic, vertical-agnostic booking agenda
=========================================

Books ``resource.resource`` records over a time span and shows them on an
interactive timeline. It knows nothing about sales, invoicing or any specific
business: verticals (motorbike rental, clinic consulting rooms, ...) extend
``primate.booking`` with their own fields and plug their own quick-create form
through the ``form_view_ref`` key of the action context.

Main concepts
-------------
* ``primate.booking``: a resource is taken by someone between two datetimes.
  Only ``confirmed`` and ``in_use`` bookings actually hold the resource;
  drafts do not block anything.
* ``primate.booking.block``: a span where the resource is unavailable for a
  reason that is not a booking (under review, maintenance, ...). A block with
  no end date is an open block and lasts until it is closed.
* ``primate.booking.block.reason``: the catalogue of block reasons.
""",
    "version": "19.0.1.0.0",
    "category": "Services",
    "author": "Primate",
    "website": "https://primate.uy",
    "license": "LGPL-3",
    "depends": [
        "mail",
        "resource",
        "web_timeline",
    ],
    "data": [
        "security/booking_security.xml",
        "security/ir.model.access.csv",
        "data/booking_block_reason_data.xml",
        "views/booking_block_reason_views.xml",
        "views/booking_block_views.xml",
        "views/booking_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
}
