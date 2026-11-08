# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.addons.base.models.ir_actions import VIEW_TYPES

from .ir_ui_view import AGENDA_VIEW

# Lista que usa ir.actions.act_window para validar view_mode.
if AGENDA_VIEW not in VIEW_TYPES:
    VIEW_TYPES.append(AGENDA_VIEW)


class ActWindowView(models.Model):
    _inherit = "ir.actions.act_window.view"

    view_mode = fields.Selection(
        selection_add=[AGENDA_VIEW],
        ondelete={"agenda": "cascade"},
    )
