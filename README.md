# Motos Rack — Odoo 19 Community

Alquiler de motos en Praia da Pipa (RN, Brasil). Moneda BRL, zona horaria
America/Fortaleza, localización `l10n_br` instalada desde el inicio.

## Módulos

| Módulo | Qué es |
|---|---|
| `primate_resource_booking` | Agenda genérica de reservas sobre `resource.resource`. **No depende de Ventas**: es reutilizable por otros verticales (el próximo es una clínica con profesionales y consultorios). |
| `motosrack_rental` | El vertical de la rentadora: motos, precios por tramos, facturación, cobros, entregas, devoluciones, prórrogas y cancelaciones. |
| `motosrack_fleet` | Planes de mantenimiento y documentos de vehículos. **Fuera de la Etapa 1 y sin instalar.** |
| `primate_fleet_rental_ext` | Correcciones heredadas sobre el `fleet_rental` de Cybrosys. Queda del enfoque anterior; no participa de la Etapa 1. |

### `primate_resource_booking`

- `primate.booking`: recurso, inicio, fin, cliente, estado
  (borrador → confirmada → en uso → terminada / cancelada), `res_model` +
  `res_id` para colgarle el documento de cada vertical.
- `primate.booking.block`: bloqueo del recurso, con fin opcional (bloqueo
  abierto) y motivo.
- `primate.booking.block.reason`: motivos con color y si quitan o no
  disponibilidad.
- `_get_availability(resource, start, stop)` devuelve disponibilidad y la
  lista de razones. Es la API que consume cualquier vertical.
- Las reservas en borrador **no** bloquean. Dos reservas confirmadas o en uso
  de un mismo recurso no pueden solaparse: lo impide un `@api.constrains` y,
  por debajo, un `EXCLUDE USING gist` sobre `tstzrange` en PostgreSQL.
- Bloqueos y reservas son independientes: pueden solaparse, se avisa, y
  ambos se ven en la agenda.
- Vistas: timeline (OCA `web_timeline`), lista, calendario y una vista
  "Operación del día" pensada para el teléfono.

### `motosrack_rental`

- Cada `fleet.vehicle` recibe un `resource_id` material automático. Ocho
  motos de demo editables, sin matrícula.
- Producto de servicio "Alquiler moto" en días, y "Casco" almacenable sin
  seguimiento individual, con ubicaciones propias para cascos alquilados y
  cascos perdidos o dañados.
- Listas de precios con tramos nativos por `min_quantity` sobre la cantidad
  de días:
  - **General**: 1→130, 4→120, 7→100, 10→90, 14→80, 21→70, 30→50
  - **Moradores**: 1→80, 4→75, 7→70, 14→60, 30→40
- Alta rápida desde la agenda: moto, fechas, cliente (alta al vuelo con
  nombre y teléfono), lista, cascos, precio y cobro.
- **Confirmar** hace todo en una transacción: valida disponibilidad, crea y
  confirma el pedido, bloquea la moto, emite la factura y registra el cobro
  conciliado en el diario elegido (Pix, Efectivo o Tarjeta), o la deja
  abierta si queda pendiente.
- Entrega y devolución con fecha real, cascos por movimientos de stock
  reales, kilometraje, combustible, notas y fotos. La devolución abre un
  bloqueo "Pendiente de revisión" que se cierra con **Liberar moto**.
- Atraso: recargo sugerido editable sobre el pedido y aviso si compromete
  la reserva siguiente. Un cron diario detecta las motos fuera de plazo.
- Prórrogas con tres criterios de precio sobre los días acumulados de toda
  la cadena: recalcular todo, días nuevos al tramo acumulado (por defecto),
  o independiente.
- Cambios de fecha o moto con revalidación, y ajuste por nota de crédito o
  factura complementaria cuando ya se facturó. Nunca se edita un documento
  publicado.
- Cancelación con asistente para decidir qué pasa con lo cobrado:
  devolución total, parcial o retención.
- Un único grupo operativo, **Motos Rack / Operador**. La contabilidad
  mantiene sus grupos estándar.

## Instalación

```bash
createdb -T template0 o19_motosrack
.venv/bin/python _shared/community/odoo-bin -c MotosRack.conf -d o19_motosrack -i base --stop-after-init
# país y moneda de la compañía: BR / BRL (si no, l10n_br no se autoinstala)
.venv/bin/python _shared/community/odoo-bin -c MotosRack.conf -d o19_motosrack \
    -i motosrack_rental --load-language=es_AR,pt_BR --stop-after-init
```

Requiere `web_timeline` de OCA/web 19.0 en el `addons_path` (en este entorno
entra por el symlink `_shared/webOCA`).

## Tests

```bash
.venv/bin/python _shared/community/odoo-bin -c MotosRack.conf -d o19_motosrack \
    -u primate_resource_booking,motosrack_rental --test-enable \
    --test-tags /motosrack_rental,/primate_resource_booking --stop-after-init
```

88 tests: 27 del módulo genérico y 61 del vertical. Cubren tramos y sus
bordes (3/4, 6/7, 29/30, 31 días) en las dos listas, borrador que no
bloquea, confirmación que bloquea, solape rechazado, reserva futura de una
moto alquilada hoy aceptada, cobro total, seña con saldo y pendiente con
cobro posterior, precio manual y recálculo, las tres fórmulas de prórroga
con los importes del pliego y una cadena de dos prórrogas, cambio de moto,
cancelación con retención parcial, entrega y devolución con un casco
faltante, bloqueo de revisión y liberación, atraso con recargo y aviso, y
bloqueo solapado permitido con aviso.

## Prueba manual en 10 minutos

Arrancar el servidor y entrar como administrador:

```bash
.venv/bin/python _shared/community/odoo-bin -c MotosRack.conf -d o19_motosrack
# http://127.0.0.1:19096
```

1. **Reservar** (2 min). *Motos Rack → Agenda*. Arrastrar un rango de 8 días
   sobre "Moto 1". Se abre el alta rápida: cliente nuevo con nombre y
   teléfono, lista **General**, 2 cascos. Tiene que mostrar 8 días a
   R$ 100 = **R$ 800** (tramo de 7 días). Elegir *Pagado total* y el diario
   **Pix**, y pulsar **Confirmar**.
2. **Verificar el cobro** (1 min). En la reserva, el botón del pedido lleva
   a la orden confirmada; la factura está publicada y pagada, y el saldo
   queda en cero.
3. **Solape** (1 min). Arrastrar otro rango sobre la misma moto que pise
   esas fechas. Al confirmar tiene que rechazarlo diciendo *Reservada*.
   Correr el mismo rango a otra moto y confirmar: pasa.
4. **Entregar** (1 min). En la primera reserva, **Deliver Bike**: fecha
   real, 2 cascos, kilometraje. La reserva pasa a *En uso* y los cascos
   salen del stock a la ubicación de alquilados.
5. **Prórroga** (2 min). **Extend**, 8 días más, criterio *días nuevos al
   tramo acumulado*. Son 16 días acumulados → tramo de 14 → R$ 80/día →
   **R$ 640** en un pedido nuevo enlazado al original. Con *recalcular todo*
   daría R$ 480 y con *independiente* R$ 800.
6. **Devolver** (2 min). **Record the return** con un casco de menos,
   marcándolo como perdido. La reserva pasa a *Terminada*, queda un bloqueo
   "Pendiente de revisión" sobre la moto, el casco perdido no vuelve al
   stock disponible y **Liberar moto** cierra el bloqueo.
7. **Operación del día** (1 min). *Motos Rack → Day of operation*: entregas
   y devoluciones de hoy agrupadas por estado. Es la vista pensada para el
   teléfono.

## Supuestos y brechas

- **`web_timeline` en el teléfono no está probado en un dispositivo real.**
  El widget de OCA usa vis-timeline; el arrastre para crear depende de
  eventos táctiles que no se verificaron. La vista "Operación del día" es
  la alternativa usable en móvil, y es donde conviene que trabaje la
  operadora si el arrastre resulta incómodo.
- **El alta rápida se impone con `form_view_ref` en el contexto de la
  acción**, sin una línea de JavaScript. Es el mecanismo estándar de Odoo
  y está verificado en ejecución. El costo es que los campos del vertical
  (cliente, lista, cascos, cobro) viven en el modelo genérico
  `primate.booking`, igual que `sale` le agrega campos a `res.partner`.
- **El timeline de OCA ata una vista a un solo modelo**, así que cada
  vertical declara la suya; no hay forma de compartir una sola agenda entre
  modelos distintos.
- **Los tres diarios de cobro se declaran también como datos del plan de
  cuentas brasileño.** En una base nueva el plan se aplica después de todos
  los `post_init_hook` y borra los diarios que existan, así que la única
  forma de que sobrevivan es que los cree el propio plan. Si algún día la
  compañía cargara un plan distinto del `br`, habría que replicar esa
  declaración para ese plan.
- **El módulo habilita listas de precios y unidades de medida para todos
  los usuarios** (`product.group_product_pricelist`, `uom.group_uom`). Sin
  lo primero, `property_product_pricelist` no resuelve y todos los clientes
  caerían en la lista por defecto en silencio.
- **El tope de tramo está apagado.** Por defecto los tramos son estrictos:
  29 días pueden costar más que 30. El parámetro
  `motosrack_rental.tier_cap_enabled` lo activa.
- **Días = `ceil((fin − inicio − tolerancia)/24h)`, mínimo 1**, con
  tolerancia de 2 horas por defecto. Más de 30 días usa el tramo de 30.
  Todo configurable en *Ajustes*.
- **Los cascos no tienen seguimiento individual**: son un producto
  almacenable y se mueven por cantidad.
- **NFS-e / NF-e electrónica está fuera de alcance.** La factura es el
  documento contable interno.
- **Los nombres de los diarios y de las motos son datos en español**
  ("Efectivo", "Tarjeta", "Moto 1"), editables desde la interfaz. El código
  y los comentarios están en inglés, con traducciones `es` y `pt_BR`.
- **Fuera de la Etapa 1**: inspecciones estructuradas, mantenimiento con
  bloqueos (salvo el motivo ya cargado como dato), racks, documentos de
  vehículos, gastos e inversiones por moto, depósitos de garantía,
  rentabilidad, distribución de gastos y panel de administración. Los
  modelos están preparados para agregarlos sin rehacerlos.
