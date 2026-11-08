# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Give a resource to the vehicles that were there before the module.

    The agenda books resources, so a vehicle without one would never show
    up on it. Vehicles created from here on get theirs on create.
    """
    vehicles = env["fleet.vehicle"].with_context(active_test=False).search(
        [("resource_id", "=", False)]
    )
    if vehicles:
        vehicles._ensure_resource()
        _logger.info("Created a booking resource for %s vehicle(s).", len(vehicles))
