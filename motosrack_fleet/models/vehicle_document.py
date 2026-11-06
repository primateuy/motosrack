# -*- coding: utf-8 -*-

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

DOCUMENT_STATE = [
    ('valid', 'Vigente'),
    ('expiring', 'Por vencer'),
    ('expired', 'Vencido'),
]


class MotosrackVehicleDocument(models.Model):
    """Documentacion de una moto con fecha de vencimiento."""

    _name = 'motosrack.vehicle.document'
    _description = 'Documento de la moto'
    _order = 'date_end asc, id desc'

    name = fields.Char(
        string='Numero / referencia',
    )
    doc_type = fields.Selection(
        selection=[
            ('crlv', 'CRLV / Licenciamento'),
            ('insurance', 'Seguro'),
            ('ipva', 'IPVA'),
            ('inspection', 'Inspeccion tecnica'),
            ('other', 'Otro'),
        ],
        string='Tipo',
        required=True,
        default='crlv',
        index=True,
    )
    vehicle_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Moto',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compania',
        related='vehicle_id.company_id',
        store=True,
        index=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Emisor / aseguradora',
        ondelete='restrict',
    )
    date_start = fields.Date(
        string='Vigente desde',
        default=fields.Date.context_today,
    )
    date_end = fields.Date(
        string='Vence el',
        required=True,
        index=True,
    )
    alert_days = fields.Integer(
        string='Avisar (dias antes)',
        default=30,
    )
    amount = fields.Monetary(
        string='Costo',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda',
        ondelete='restrict',
        default=lambda self: self.env.company.currency_id,
    )
    document_file = fields.Binary(
        string='Archivo',
        attachment=True,
        copy=False,
    )
    document_filename = fields.Char(
        string='Nombre del archivo',
        copy=False,
    )
    note = fields.Text(
        string='Notas',
    )
    state = fields.Selection(
        selection=DOCUMENT_STATE,
        string='Estado',
        compute='_compute_state',
        search='_search_state',
        help='Se calcula contra la fecha de hoy, por eso no se almacena.',
    )
    days_to_expiry = fields.Integer(
        string='Dias para vencer',
        compute='_compute_state',
    )

    @api.depends('date_end', 'alert_days')
    def _compute_state(self):
        hoy = fields.Date.context_today(self)
        for doc in self:
            if not doc.date_end:
                doc.state = 'valid'
                doc.days_to_expiry = 0
                continue
            faltan = (doc.date_end - hoy).days
            doc.days_to_expiry = faltan
            if faltan < 0:
                doc.state = 'expired'
            elif faltan <= doc.alert_days:
                doc.state = 'expiring'
            else:
                doc.state = 'valid'

    def _search_state(self, operator, value):
        """Traduce el estado calculado a un dominio sobre fechas.

        Args:
            operator (str): '=', '!=', 'in' o 'not in'.
            value: estado o lista de estados buscados.

        Returns:
            list: dominio sobre ids de motosrack.vehicle.document.
        """
        if operator in ('=', '!='):
            buscados = {value}
        elif operator in ('in', 'not in'):
            buscados = set(value)
        else:
            raise NotImplementedError(_(
                'El filtro por estado del documento no admite el operador '
                '"%s".', operator,
            ))

        coincidentes = self.search([]).filtered(
            lambda doc: doc.state in buscados
        )
        negado = operator in ('!=', 'not in')
        return [('id', 'not in' if negado else 'in', coincidentes.ids)]

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for doc in self:
            if doc.date_start and doc.date_end and doc.date_end < doc.date_start:
                raise ValidationError(_(
                    'El documento "%s" no puede vencer antes de empezar a '
                    'ser vigente.', doc.display_name,
                ))

    @api.depends('doc_type', 'name', 'vehicle_id')
    def _compute_display_name(self):
        """Identifica el documento por tipo y moto, como se lo busca."""
        tipos = dict(self._fields['doc_type']._description_selection(self.env))
        for doc in self:
            etiqueta = tipos.get(doc.doc_type, _('Documento'))
            if doc.name:
                etiqueta = '%s %s' % (etiqueta, doc.name)
            if doc.vehicle_id:
                etiqueta = '%s - %s' % (etiqueta, doc.vehicle_id.display_name)
            doc.display_name = etiqueta

    def action_renew(self):
        """Duplica el documento con la vigencia corrida un ano hacia adelante."""
        self.ensure_one()
        nuevo = self.copy({
            'date_start': self.date_end + timedelta(days=1),
            'date_end': self.date_end + timedelta(days=366),
            'name': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Renovar documento'),
            'res_model': self._name,
            'res_id': nuevo.id,
            'view_mode': 'form',
            'target': 'current',
        }
