# -*- coding: utf-8 -*-

from odoo import fields, models

# El tipo de vista se deduce de la etiqueta raiz del arch, asi que un
# <agenda> solo es valido si "agenda" esta en esta seleccion.
AGENDA_VIEW = ("agenda", "Agenda")


class IrUIView(models.Model):
    _inherit = "ir.ui.view"

    type = fields.Selection(selection_add=[AGENDA_VIEW])
