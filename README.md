# Motos Rack — Odoo 19 Community

Alquiler de motos en Praia da Pipa (RN, Brasil). Moneda BRL, zona horaria
America/Fortaleza, localización `l10n_br`.

El desarrollo está partido en tres: una agenda genérica, un vertical de
alquiler de vehículos y, encima, los datos de este cliente. Nada de lo que
dice "Motos Rack" vive en los dos primeros.

## Módulos

Las dos capas reutilizables **ya no viven en este repo**: se extrajeron a
[`PrimateUy-SAS/primate_booking`](https://github.com/PrimateUy-SAS/primate_booking)
(rama `19.0`), para que las consuma cualquier cliente sin copiarlas. Acá queda
sólo lo de Motos Rack.

| Módulo | Repo | Qué es |
|---|---|---|
| `primate_resource_booking` | `primate_booking` | Agenda genérica de reservas sobre `resource.resource`. **No depende de Ventas**: la reutiliza cualquier vertical (el próximo es una clínica con profesionales y consultorios). |
| `primate_vehicle_rental` | `primate_booking` | Alquiler de vehículos de la flota: precios por tramos, facturación, cobros, entregas, devoluciones, prórrogas y cancelaciones. No sabe nada de Pipa ni de motos: sirve para autos, bicis o cuatriciclos. |
| `motosrack` | este repo | Lo que es de este negocio y de ningún otro: las ocho Honda Pop, las listas General y Moradores, y los diarios Pix, Efectivo y Tarjeta. |
| `motosrack_fleet` | este repo | Planes de mantenimiento y documentos de vehículos. **Fuera de la Etapa 1 y sin instalar.** |
| `primate_fleet_rental_ext` | este repo | Correcciones heredadas sobre el `fleet_rental` de Cybrosys. Queda del enfoque anterior; no participa de la Etapa 1. |

Los dos primeros se clonan en `shared/primateuy/primate_booking-19.0` y entran
al `addons_path` por el symlink `_shared/primate_booking`. **No se editan desde
este proyecto**: los cambios van al repo compartido, que afecta a todos los
clientes que lo usen.

La agenda es una vista propia de Odoo (tipo `agenda`), escrita en OWL: no
depende de ninguna librería de calendario de terceros. La única dependencia
externa es OCA `web_responsive`, para que la interfaz sea usable en el
teléfono.

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
- Vistas: agenda, lista, calendario y una vista "Operación del día" pensada
  para el teléfono.
- **La vista agenda** es un tipo de vista propio, registrado como los
  nativos. El arch la configura entera, así que cualquier vertical arma la
  suya heredando y cambiando atributos:

  ```xml
  <agenda date_start="start" date_stop="stop" group_by="resource_id"
          label="partner_id" state="state" chain="parent_booking_id"
          group_domain="[('vehicle_ids', '!=', False)]"
          overlay_model="primate.booking.block"/>
  ```

  Muestra **todos** los recursos como filas, tengan o no reservas; se reserva
  arrastrando sobre la fila; una barra se mueve arrastrándola y se estira
  desde los bordes; y los bloqueos del `overlay_model` se dibujan rayados en
  la misma fila, de modo que una reserva y un bloqueo se ven a la vez sin
  taparse. La operadora elige escala, densidad y estilo de barra, y esas tres
  preferencias le quedan guardadas.

### `primate_vehicle_rental`

- Cada `fleet.vehicle` recibe un `resource_id` material automático.
- Producto de servicio "Vehicle rental" en días (traducido a "Alquiler de
  vehículo") y "Helmet" almacenable sin seguimiento individual, con
  ubicaciones propias para cascos alquilados y cascos perdidos o dañados.
- Precios por tramos con reglas nativas `min_quantity` sobre la cantidad de
  días: la tarifa del tramo que corresponde al total se aplica a todos los
  días.
- Alta rápida desde la agenda: vehículo, fechas, cliente (alta al vuelo con
  nombre y teléfono), lista, cascos, precio y cobro.
- **Confirmar** hace todo en una transacción: valida disponibilidad, crea y
  confirma el pedido, bloquea el vehículo, emite la factura y registra el
  cobro conciliado en el diario elegido, o la deja abierta si queda
  pendiente.
- Entrega y devolución con fecha real, cascos por movimientos de stock
  reales, kilometraje, combustible, notas y fotos. La devolución abre un
  bloqueo "Pendiente de revisión" que se cierra con **Liberar vehículo**.
- Atraso: recargo sugerido editable sobre el pedido y aviso si compromete
  la reserva siguiente. Un cron diario detecta los vehículos fuera de plazo.
- Prórrogas con tres criterios de precio sobre los días acumulados de toda
  la cadena: recalcular todo, días nuevos al tramo acumulado (por defecto),
  o independiente.
- Cambios de fecha o vehículo con revalidación, y ajuste por nota de crédito
  o factura complementaria cuando ya se facturó. Nunca se edita un documento
  publicado.
- Cancelación con asistente para decidir qué pasa con lo cobrado:
  devolución total, parcial o retención.
- Un único grupo operativo, **Alquiler / Operador**, que se le asigna al
  administrador al instalar. La contabilidad mantiene sus grupos estándar.
- La lista de precios de una reserva sale de la que el cliente tenga
  asignada **a propósito**; si no tiene, de la configurada en Ajustes.

### `motosrack`

- Las ocho Honda Pop, editables (`noupdate`), cada una con su recurso.
- **General**: 1→130, 4→120, 7→100, 10→90, 14→80, 21→70, 30→50
- **Moradores**: 1→80, 4→75, 7→70, 14→60, 30→40
- Diarios Pix, Efectivo y Tarjeta, declarados **también** como datos del
  plan de cuentas brasileño: en una base nueva el plan se aplica después de
  todos los `post_init_hook` y borra los diarios existentes, así que la
  única forma de que sobrevivan es que los cree el propio plan.
- Nombra las ubicaciones de cascos en castellano (`stock.location.name` no
  es traducible), respetando cualquier nombre ya cambiado a mano.

## Instalación

```bash
createdb -T template0 o19_motosrack
.venv/bin/python _shared/community/odoo-bin -c MotosRack.conf -d o19_motosrack -i base --stop-after-init
# país y moneda de la compañía: BR / BRL (si no, l10n_br no se autoinstala)
.venv/bin/python _shared/community/odoo-bin -c MotosRack.conf -d o19_motosrack \
    -i motosrack,web_responsive --load-language=es_AR,pt_BR --stop-after-init
```

Instalar `motosrack` arrastra `primate_vehicle_rental`,
`primate_resource_booking` y `l10n_br`. Los dos primeros salen del repo
compartido, así que el `addons_path` tiene que incluir
`_shared/primate_booking` (ya está en `MotosRack.conf`).

Para otro cliente se instala sólo `primate_vehicle_rental` desde el mismo repo
compartido, y se cargan sus propios vehículos y listas.

## Tests

```bash
.venv/bin/python _shared/community/odoo-bin -c MotosRack.conf -d o19_motosrack \
    -u primate_resource_booking,primate_vehicle_rental,motosrack --test-enable \
    --test-tags /primate_resource_booking,/primate_vehicle_rental,/motosrack \
    --stop-after-init
```

96 tests: 27 de la agenda genérica, 64 del vertical y 5 de los datos del
cliente. El vertical **no depende de los datos de Motos Rack**: arma sus
propios vehículos, listas y diarios, así que se puede probar solo. Cubren
tramos y sus bordes (3/4, 6/7, 29/30, 31 días) en las dos listas, borrador
que no bloquea, confirmación que bloquea, solape rechazado, reserva futura
de un vehículo alquilado hoy aceptada, cobro total, seña con saldo y
pendiente con cobro posterior, precio manual y recálculo, las tres fórmulas
de prórroga con los importes del pliego y una cadena de dos prórrogas,
cambio de vehículo, cancelación con retención parcial, entrega y devolución
con un casco faltante, bloqueo de revisión y liberación, atraso con recargo
y aviso, bloqueo solapado permitido con aviso, y el alta rápida que resuelve
el vehículo desde la fila de la agenda.

## Prueba manual en 10 minutos

Arrancar el servidor y entrar como administrador:

```bash
.venv/bin/python _shared/community/odoo-bin -c MotosRack.conf -d o19_motosrack
# http://127.0.0.1:19096
```

1. **Reservar** (2 min). *Alquiler → Agenda*. Las ocho motos aparecen como
   filas aunque no haya ninguna reserva. **Arrastrá** sobre la fila de
   "Moto 1" marcando ocho días: mientras arrastrás se pinta la banda con las
   fechas, y al soltar se abre el alta rápida con esa moto y ese rango.
   Cliente nuevo con nombre y teléfono, lista **General**, 2 cascos. Tiene
   que mostrar 8 días a R$ 100 = **R$ 800** (tramo de 7 días). Elegir
   *Pagado total* y el diario **Pix**, y pulsar **Confirmar**.
2. **Verificar el cobro** (1 min). En la reserva, el botón del pedido lleva
   a la orden confirmada; la factura está publicada y pagada, y el saldo
   queda en cero.
3. **Solape** (1 min). Crear otra reserva sobre la misma moto que pise esas
   fechas. Al confirmar tiene que rechazarla diciendo *Reservada*. La misma
   reserva en otra moto pasa. Lo mismo arrastrando una barra confirmada
   encima de otra: el servidor la rechaza y la barra vuelve a su lugar.
4. **Entregar** (1 min). En la primera reserva, **Entregar vehículo**: fecha
   real, 2 cascos, kilometraje. La reserva pasa a *En uso* y los cascos
   salen del stock a la ubicación de alquilados.
5. **Prórroga** (2 min). **Extender**, 8 días más, criterio *días nuevos al
   tramo acumulado*. Son 16 días acumulados → tramo de 14 → R$ 80/día →
   **R$ 640** en un pedido nuevo enlazado al original. Con *recalcular todo*
   daría R$ 480 y con *independiente* R$ 800.
6. **Devolver** (2 min). **Devolver vehículo** con un casco de menos,
   marcándolo como perdido. La reserva pasa a *Terminada*, queda un bloqueo
   "Pendiente de revisión" sobre la moto, el casco perdido no vuelve al
   stock disponible y **Liberar vehículo** cierra el bloqueo.
7. **Operación del día** (1 min). *Alquiler → Operación del día*: entregas
   y devoluciones de hoy agrupadas por estado. Es la vista pensada para el
   teléfono.

## Supuestos y brechas

- **La agenda en el teléfono no está probada en un dispositivo real.** Los
  gestos usan eventos de puntero, que en teoría cubren el táctil, y la
  grilla se angosta sola; nada de eso se verificó sobre un teléfono. La
  vista "Operación del día" sigue siendo la alternativa para trabajar desde
  el móvil.
- **La escala más fina de la agenda es el día.** Alcanza para alquileres,
  pero un vertical que agende por horas (turnos de taller, consultorios)
  necesita columnas de hora: la vista está escrita para admitirlas, pero no
  están implementadas.
- **Los estilos de barra se guardan en el navegador.** Si la operadora
  cambia de máquina, vuelve a los valores por defecto. Pasarlo a una
  preferencia de `res.users` es un cambio chico si hace falta.
- **El alta rápida se impone con `form_view_ref` en el contexto de la
  acción**, sin una línea de JavaScript. Es el mecanismo estándar de Odoo
  y está verificado en ejecución. El costo es que los campos del vertical
  (cliente, lista, cascos, cobro) viven en el modelo genérico
  `primate.booking`, igual que `sale` le agrega campos a `res.partner`.
- **`web_responsive` viene de OCA/web 19.0** (19.0.1.1.1), no del fork
  `primateuy/webOCA`, cuya rama 19.0 está algunos commits atrás. Si hay una
  razón para usar el fork, se cambia con un checkout.
- **El módulo habilita listas de precios y unidades de medida para todos
  los usuarios** (`product.group_product_pricelist`, `uom.group_uom`). Sin
  lo primero, `property_product_pricelist` no resuelve y todos los clientes
  caerían en la lista por defecto en silencio.
- **El tope de tramo está apagado.** Por defecto los tramos son estrictos:
  29 días pueden costar más que 30. El parámetro
  `primate_vehicle_rental.tier_cap_enabled` lo activa.
- **Días = `ceil((fin − inicio − tolerancia)/24h)`, mínimo 1**, con
  tolerancia de 2 horas por defecto. Más de 30 días usa el tramo de 30.
  Todo configurable en *Ajustes*.
- **Los cascos no tienen seguimiento individual**: son un producto
  almacenable y se mueven por cantidad.
- **NFS-e / NF-e electrónica está fuera de alcance.** La factura es el
  documento contable interno.
- **El código y los comentarios están en inglés**, con traducciones `es` y
  `pt_BR` completas. Los nombres de los diarios y de las motos son datos
  del módulo del cliente, editables desde la interfaz.
- **Fuera de la Etapa 1**: inspecciones estructuradas, mantenimiento con
  bloqueos (salvo el motivo ya cargado como dato), racks, documentos de
  vehículos, gastos e inversiones por moto, depósitos de garantía,
  rentabilidad, distribución de gastos y panel de administración. Los
  modelos están preparados para agregarlos sin rehacerlos.
