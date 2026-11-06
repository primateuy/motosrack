# -*- coding: utf-8 -*-

import logging
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _

_logger = logging.getLogger(__name__)

MAINTENANCE_STATE = [
    ('none', 'Sin plan'),
    ('ok', 'Al dia'),
    ('soon', 'Service proximo'),
    ('overdue', 'Service vencido'),
]


class FleetVehicle(models.Model):
    """Agrega a la moto el seguimiento de su mantenimiento preventivo."""

    _inherit = 'fleet.vehicle'

    maintenance_plan_id = fields.Many2one(
        comodel_name='motosrack.maintenance.plan',
        string='Plan de mantenimiento',
        ondelete='set null',
        compute='_compute_maintenance_plan_id',
        store=True,
        readonly=False,
        index='btree_not_null',
        help='Se asigna solo segun el modelo de la moto, pero puede cambiarse '
             'a mano para un vehiculo concreto.',
    )
    last_service_date = fields.Date(
        string='Ultimo service',
        compute='_compute_last_service',
        store=True,
    )
    last_service_odometer = fields.Float(
        string='Odometro del ultimo service',
        compute='_compute_last_service',
        store=True,
    )
    next_service_date = fields.Date(
        string='Proximo service (fecha)',
        compute='_compute_next_service',
        store=True,
    )
    next_service_odometer = fields.Float(
        string='Proximo service (odometro)',
        compute='_compute_next_service',
        store=True,
    )
    km_to_next_service = fields.Float(
        string='Km para el service',
        compute='_compute_maintenance_state',
    )
    days_to_next_service = fields.Integer(
        string='Dias para el service',
        compute='_compute_maintenance_state',
    )
    maintenance_state = fields.Selection(
        selection=MAINTENANCE_STATE,
        string='Estado de mantenimiento',
        compute='_compute_maintenance_state',
        search='_search_maintenance_state',
        help='Depende del odometro actual, que Odoo calcula al vuelo, por eso '
             'este campo no se almacena.',
    )
    document_ids = fields.One2many(
        comodel_name='motosrack.vehicle.document',
        inverse_name='vehicle_id',
        string='Documentacion',
    )
    document_count = fields.Integer(
        string='Documentos',
        compute='_compute_document_count',
    )
    has_expired_document = fields.Boolean(
        string='Documentacion vencida',
        compute='_compute_document_count',
    )

    # -------------------------------------------------------------------
    # COMPUTES
    # -------------------------------------------------------------------

    @api.depends('model_id')
    def _compute_maintenance_plan_id(self):
        """Asigna el plan que cubre el modelo de la moto."""
        Plan = self.env['motosrack.maintenance.plan']
        for vehicle in self:
            if vehicle.maintenance_plan_id:
                continue
            vehicle.maintenance_plan_id = Plan.search([
                ('model_ids', 'in', vehicle.model_id.ids),
                ('company_id', '=', (vehicle.company_id or self.env.company).id),
            ], limit=1)

    @api.depends(
        'maintenance_plan_id',
        'log_services.state',
        'log_services.date',
        'log_services.service_type_id',
        'log_services.odometer_id.value',
    )
    def _compute_last_service(self):
        """Busca el ultimo service hecho del tipo que programa el plan."""
        for vehicle in self:
            plan = vehicle.maintenance_plan_id
            if not plan:
                vehicle.last_service_date = False
                vehicle.last_service_odometer = 0.0
                continue
            hechos = vehicle.log_services.filtered(
                lambda log: log.state == 'done'
                and log.service_type_id == plan.service_type_id
                and log.date
            ).sorted('date', reverse=True)
            if hechos:
                vehicle.last_service_date = hechos[0].date
                vehicle.last_service_odometer = hechos[0].odometer_id.value
            else:
                vehicle.last_service_date = False
                vehicle.last_service_odometer = 0.0

    @api.depends(
        'maintenance_plan_id.interval_km',
        'maintenance_plan_id.interval_months',
        'last_service_date',
        'last_service_odometer',
        'acquisition_date',
    )
    def _compute_next_service(self):
        """Proyecta el proximo service desde el ultimo hecho o desde el alta."""
        for vehicle in self:
            plan = vehicle.maintenance_plan_id
            if not plan:
                vehicle.next_service_date = False
                vehicle.next_service_odometer = 0.0
                continue

            if plan.interval_months:
                base_date = vehicle.last_service_date or vehicle.acquisition_date
                vehicle.next_service_date = (
                    base_date + relativedelta(months=plan.interval_months)
                    if base_date else False
                )
            else:
                vehicle.next_service_date = False

            if plan.interval_km:
                vehicle.next_service_odometer = (
                    vehicle.last_service_odometer + plan.interval_km
                )
            else:
                vehicle.next_service_odometer = 0.0

    def _compute_maintenance_state(self):
        """Clasifica la moto segun cuanto falta para el proximo service."""
        hoy = fields.Date.context_today(self)
        for vehicle in self:
            plan = vehicle.maintenance_plan_id
            vehicle.km_to_next_service = 0.0
            vehicle.days_to_next_service = 0
            if not plan:
                vehicle.maintenance_state = 'none'
                continue

            vencido = False
            proximo = False

            if vehicle.next_service_odometer:
                faltan_km = vehicle.next_service_odometer - vehicle.odometer
                vehicle.km_to_next_service = faltan_km
                if faltan_km <= 0:
                    vencido = True
                elif faltan_km <= plan.alert_km:
                    proximo = True

            if vehicle.next_service_date:
                faltan_dias = (vehicle.next_service_date - hoy).days
                vehicle.days_to_next_service = faltan_dias
                if faltan_dias <= 0:
                    vencido = True
                elif faltan_dias <= plan.alert_days:
                    proximo = True

            if vencido:
                vehicle.maintenance_state = 'overdue'
            elif proximo:
                vehicle.maintenance_state = 'soon'
            else:
                vehicle.maintenance_state = 'ok'

    def _search_maintenance_state(self, operator, value):
        """Permite filtrar por un campo que se calcula al vuelo.

        Args:
            operator (str): '=', '!=', 'in' o 'not in'.
            value: estado o lista de estados buscados.

        Returns:
            list: dominio sobre ids de fleet.vehicle.
        """
        if operator in ('=', '!='):
            buscados = {value}
        elif operator in ('in', 'not in'):
            buscados = set(value)
        else:
            raise NotImplementedError(_(
                'El filtro por estado de mantenimiento no admite el operador '
                '"%s".', operator,
            ))

        candidatos = self.search([])
        coincidentes = candidatos.filtered(
            lambda vehicle: vehicle.maintenance_state in buscados
        )
        negado = operator in ('!=', 'not in')
        return [('id', 'not in' if negado else 'in', coincidentes.ids)]

    def _compute_document_count(self):
        """Cuenta los documentos y avisa si alguno esta vencido."""
        for vehicle in self:
            vehicle.document_count = len(vehicle.document_ids)
            vehicle.has_expired_document = any(
                doc.state == 'expired' for doc in vehicle.document_ids
            )

    # -------------------------------------------------------------------
    # ACCIONES
    # -------------------------------------------------------------------

    def action_view_documents(self):
        """Abre la documentacion de la moto."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Documentacion de %s', self.display_name),
            'res_model': 'motosrack.vehicle.document',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

    # -------------------------------------------------------------------
    # TAREA PROGRAMADA
    # -------------------------------------------------------------------

    @api.model
    def _cron_check_maintenance(self):
        """Crea actividades por services y documentos vencidos o proximos.

        Se salta las motos que ya tienen una actividad abierta con el mismo
        aviso, para no repetir el recordatorio cada dia.
        """
        vehiculos = self.search([('active', '=', True)])
        creadas = 0
        for vehicle in vehiculos:
            estado = vehicle.maintenance_state
            if estado in ('soon', 'overdue'):
                resumen = (
                    _('Service vencido: %s', vehicle.display_name)
                    if estado == 'overdue'
                    else _('Service proximo: %s', vehicle.display_name)
                )
                if vehicle._schedule_fleet_activity(resumen, vehicle._maintenance_note()):
                    creadas += 1

            vencidos = vehicle.document_ids.filtered(
                lambda doc: doc.state in ('expiring', 'expired')
            )
            for doc in vencidos:
                resumen = _('Documentacion %(estado)s: %(doc)s',
                            estado=_('vencida') if doc.state == 'expired'
                            else _('por vencer'),
                            doc=doc.display_name)
                nota = _('%(doc)s vence el %(fecha)s.',
                         doc=doc.display_name, fecha=doc.date_end)
                if vehicle._schedule_fleet_activity(resumen, nota):
                    creadas += 1

        _logger.info('MotosRack: %s actividades de flota creadas.', creadas)
        return creadas

    def _maintenance_note(self):
        """Texto del aviso de service con los datos concretos de la moto."""
        self.ensure_one()
        partes = []
        if self.next_service_odometer:
            partes.append(_(
                'Proximo service a los %(objetivo)s km (odometro actual: '
                '%(actual)s km).',
                objetivo=int(self.next_service_odometer),
                actual=int(self.odometer),
            ))
        if self.next_service_date:
            partes.append(_(
                'Fecha prevista: %s.', self.next_service_date,
            ))
        return ' '.join(partes) or _('Revisar el plan de mantenimiento.')

    def _schedule_fleet_activity(self, resumen, nota):
        """Programa una actividad si no hay ya una abierta con el mismo resumen.

        Args:
            resumen (str): titulo de la actividad.
            nota (str): cuerpo del aviso.

        Returns:
            bool: True si se creo la actividad.
        """
        self.ensure_one()
        ya_existe = self.env['mail.activity'].search_count([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('summary', '=', resumen),
        ])
        if ya_existe:
            return False
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=resumen,
            note=nota,
            user_id=(self.manager_id or self.env.user).id,
        )
        return True
