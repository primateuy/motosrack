# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MotosrackMaintenancePlan(models.Model):
    """Plan de mantenimiento preventivo aplicable a uno o varios modelos."""

    _name = 'motosrack.maintenance.plan'
    _description = 'Plan de mantenimiento de la flota'
    _order = 'name'

    name = fields.Char(
        string='Nombre',
        required=True,
        translate=True,
    )
    active = fields.Boolean(
        string='Activo',
        default=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Compania',
        ondelete='cascade',
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    service_type_id = fields.Many2one(
        comodel_name='fleet.service.type',
        string='Tipo de service',
        ondelete='restrict',
        required=True,
        domain="[('category', '=', 'service')]",
        help='Tipo de service que este plan programa. Se usa para encontrar '
             'el ultimo service hecho a cada moto.',
    )
    model_ids = fields.Many2many(
        comodel_name='fleet.vehicle.model',
        relation='motosrack_maintenance_plan_model_rel',
        column1='plan_id',
        column2='model_id',
        string='Modelos de moto',
        help='Modelos a los que se asigna el plan automaticamente.',
    )
    interval_km = fields.Integer(
        string='Cada (km)',
        help='Kilometros entre un service y el siguiente. 0 para no programar '
             'por kilometraje.',
    )
    interval_months = fields.Integer(
        string='Cada (meses)',
        help='Meses entre un service y el siguiente. 0 para no programar por '
             'tiempo.',
    )
    alert_km = fields.Integer(
        string='Avisar (km antes)',
        default=300,
    )
    alert_days = fields.Integer(
        string='Avisar (dias antes)',
        default=15,
    )
    note = fields.Text(
        string='Trabajos incluidos',
    )
    vehicle_ids = fields.One2many(
        comodel_name='fleet.vehicle',
        inverse_name='maintenance_plan_id',
        string='Motos',
    )
    vehicle_count = fields.Integer(
        string='Motos',
        compute='_compute_vehicle_count',
    )

    def _compute_vehicle_count(self):
        grouped = self.env['fleet.vehicle']._read_group(
            domain=[('maintenance_plan_id', 'in', self.ids)],
            groupby=['maintenance_plan_id'],
            aggregates=['__count'],
        )
        counts = {plan.id: count for plan, count in grouped}
        for plan in self:
            plan.vehicle_count = counts.get(plan.id, 0)

    @api.constrains('interval_km', 'interval_months')
    def _check_intervals(self):
        """Un plan que no programa ni por km ni por tiempo no sirve de nada."""
        for plan in self:
            if plan.interval_km <= 0 and plan.interval_months <= 0:
                raise ValidationError(_(
                    'El plan "%s" tiene que programar el service por '
                    'kilometraje, por tiempo, o por ambos.', plan.name,
                ))
            if plan.interval_km < 0 or plan.interval_months < 0:
                raise ValidationError(_(
                    'Los intervalos del plan "%s" no pueden ser negativos.',
                    plan.name,
                ))

    def action_view_vehicles(self):
        """Abre las motos que siguen este plan."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Motos con el plan %s', self.name),
            'res_model': 'fleet.vehicle',
            'view_mode': 'list,form',
            'domain': [('maintenance_plan_id', '=', self.id)],
            'context': {'default_maintenance_plan_id': self.id},
        }
