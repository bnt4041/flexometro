# Obras — ERP de construcción

Presupuestación, ejecución y cobro de obra. El núcleo del negocio es la
presupuestación según el sistema clásico español de mediciones y presupuestos
(modelo de Ramírez de Arellano):

```
Precio de suministro → Precio básico → Precio auxiliar → Precio unitario
                            → Medición → Presupuesto (capítulos y partidas)
```

## Estado: Fase 12 — usuarios, grupos y permisos por módulo

| | |
|---|---|
| Backend | FastAPI, modular por dominio |
| Base de datos | PostgreSQL 16, un schema por módulo |
| Migraciones | Alembic, una rama por módulo |
| Frontend | React 19 + TypeScript + Vite |
| Auth | Keycloak (JWT + PKCE), rol de BD de mínimo privilegio |
| Multi-tenant | RLS forzado en PostgreSQL sobre todas las tablas de negocio |
| Despliegue | Docker Compose, etiquetas Traefik listas |

### Fases

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Andamiaje: módulos, tenancy, migraciones, shell | hecha |
| 1 | Maestros: terceros y catálogo | hecha |
| 2 | Núcleo de precios: concepto + descomposición, recálculo en cascada | hecha |
| 3 | Presupuesto: capítulos, partidas, mediciones, PEM→PEC | hecha |
| 4 | Cierre de presupuestación: versionado, plantillas, informes | hecha |
| 5 | FIEBDC-3 (BC3) | hecha, sin validar contra un banco real |
| 6 | Keycloak y multi-tenant real | hecha |
| 7 | Obra: compras, albaranes, personal, coste real | hecha |
| 8 | Certificaciones, facturación y cobro (Veri\*Factu/Facturae vía n8n) | hecha, envío real vía n8n pendiente del flujo del usuario |
| 9 | IA de patrones de presupuesto (DeepSeek) | hecha |
| 10 | IA de medición desde planos (Gemini) | hecha, primer slice: planos acotados; foto/vídeo de obra ejecutada queda pendiente |
| 11 | Administración de organizaciones, tarifas, cobros y ajustes globales | hecha |
| 12 | Usuarios, grupos y permisos por módulo (ver/editar, todos/propios) | hecha |
| 13 | Big data de precios sectorial | |

## Arrancar

```bash
cp .env.example .env
docker compose up -d --build
```

- Aplicación: http://localhost:5173
- API y documentación: http://localhost:8000/docs
- Salud: http://localhost:8000/health

Todo corre en contenedor, incluidos uvicorn y el servidor de desarrollo de
Vite: no hace falta Python ni Node en el host.

Para probar el enrutado de producción con Traefik en lugar de los puertos
publicados:

```bash
docker compose --profile proxy up -d
# http://obras.localhost
```

## Arquitectura

### Módulos

Cada módulo de negocio vive en `backend/app/modules/<código>/` y declara un
`ModuleSpec` en su `__init__.py`: código, router, dependencias y las entradas de
menú que publica al frontend. Se registran en `backend/app/modules/__init__.py`.

Los módulos se activan **por organización**. El router se monta siempre pero
queda tras `require_module(...)`, de modo que un módulo desactivado responde 404
en vez de existir a medias. Activar un módulo arrastra sus dependencias;
desactivarlo falla con 409 si otro módulo activo depende de él.

La pantalla de Ajustes permite activarlos y desactivarlos, y el menú lateral se
reconstruye solo: la navegación del frontend sale del registro del backend.

Grafo de módulos:

```
core          (siempre activo)
terceros      (base)
catalogo      -> terceros
presupuestos  -> catalogo
obras         -> presupuestos
compras       -> obras, catalogo
facturacion   -> obras, terceros
ia            -> presupuestos
```

El conjunto activo se devuelve siempre cerrado bajo dependencias: si un módulo
gana una dependencia nueva en una versión posterior, esta se activa sola en vez
de dejar datos activos sin la base que necesitan.

### Maestros (Fase 1)

**Terceros** — una sola ficha `tercero` con roles (`es_cliente`,
`es_proveedor`, `es_subcontratista`) en lugar de tablas separadas: en
construcción es corriente que la misma empresa te suministre material y te
contrate obra. `contacto` son personas, y pueden existir sin empresa.

Incluye lo que el sector español necesita de verdad: NIF/NIE/CIF con validación
de dígito de control, retención de IRPF, inversión del sujeto pasivo
(art. 84.Uno.2.º f LIVA, lo normal en obra subcontratada) y número de REA con su
caducidad (Ley 32/2006).

**Catálogo** — `producto` es el catálogo comercial y logístico; `familia` lo
clasifica en árbol; `precio_suministro` une producto + proveedor + fecha y es el
primer eslabón de la cadena de precios.

El catálogo está deliberadamente separado del `concepto` de presupuestación que
llega en Fase 2. Importar un banco BEDEC en Fase 5 trae decenas de miles de
conceptos que no tienen nada que hacer en el catálogo propio de la empresa.

`precio_suministro` guarda cuatro decimales: las tarifas de proveedor llegan así
(material a granel, tornillería), y el redondeo a dos de la convención Presto se
aplica al encadenar conceptos, a partir del precio básico.

### Núcleo de precios (Fase 2)

Una sola tabla `concepto` para básicos, auxiliares y unitarios, más
`descomposicion` (padre, hijo, rendimiento, factor). Son el mismo objeto en
distinto nivel del árbol, que es como lo modela FIEBDC-3 (registros `~C` y
`~D`): así un auxiliar puede contener otro auxiliar, y un unitario funcional
agrupar unitarios, sin casos especiales.

`concepto.origen_precio` gobierna el cálculo:

| valor | de dónde sale el precio |
|---|---|
| `manual` | lo teclea una persona y nadie lo pisa |
| `producto` | de la tarifa preferente del producto en el catálogo |
| `descomposicion` | de la suma de sus hijos |

**Recálculo en cascada.** El precio está materializado en la tabla —un
presupuesto de miles de partidas no puede recorrer el árbol en cada lectura—,
así que todo cambio se propaga hacia arriba. `ancestros_en_orden` sube por una
CTE recursiva y ordena por distancia **máxima** al nodo de partida, que es un
orden topológico válido: importa con rombos, cuando un auxiliar entra en dos
unitarios que a su vez entran en el mismo funcional.

El disparo desde el catálogo va por el bus de eventos de `app/core/events.py`:
`catalogo` emite que una tarifa ha cambiado sin saber quién escucha, y
`presupuestos` se suscribe al registrarse. Es lo que permite que la cascada
funcione respetando la dirección de las dependencias, porque `catalogo` no
puede importar `presupuestos`.

**Redondeo.** Se redondea el importe de cada línea del descompuesto a dos
decimales y después se suma, con ROUND_HALF_UP. Es lo que hace que el
descompuesto impreso cuadre columna a columna; sumar con todos los decimales y
redondear al final produce descuadres de céntimos entre el papel y el total.

**Protecciones.** Los ciclos se impiden al insertar (CTE recursiva descendente
desde el hijo), la FK `descomposicion.hijo_id` es `RESTRICT` para que borrar un
concepto en uso falle en vez de vaciar el descompuesto de otro, y el recorrido
tiene un tope de profundidad como red de seguridad.

La clase del unitario (simple, complejo o funcional) **no se almacena**: se
deduce de los tipos de sus hijos, porque la clasificación se sigue de la
estructura y no al revés.

### Presupuesto (Fase 3)

`presupuesto` → `capitulo` (árbol de profundidad libre) → `partida` →
`linea_medicion`. Son tablas propias, no tipos de `Concepto`: una partida lleva
datos que solo existen dentro de su presupuesto —su medición, su sitio en un
capítulo y el precio con el que se cerró—, así que el mismo unitario usado en
dos obras necesitaría dos filas de concepto y el cuadro de precios se llenaría
de casi-duplicados.

Una partida **copia** del concepto su código, descripción, unidad y precio.
`concepto_id` es opcional: sin él es una partida alzada, con su precio a mano.

**Medición.** Réplica del registro `~M` de FIEBDC-3: comentario, uds, longitud,
anchura y altura. El parcial es el producto de lo que esté informado, y lo que
no lo esté vale 1, no 0 — una línea con solo `uds = 5` mide 5. Un cero explícito
sí anula, y un negativo deduce, que es como se descuentan los huecos.

**Encadenado.** PEM (suma de los capítulos raíz) → + gastos generales
+ beneficio industrial, ambos **sobre el PEM** y no en cascada → PEC sin IVA →
+ IVA → total. Los valores por defecto son 13 % y 6 % (RD 1098/2001). Con
inversión del sujeto pasivo el IVA queda a cero.

**El cerrojo de precios.** La cascada llega hasta las partidas, pero solo de los
presupuestos en borrador. Al salir de borrador, `precios_bloqueados` se pone a
true y el presupuesto deja de moverse: uno emitido no puede cambiar bajo los
pies de quien lo firmó. Si el cuadro se mueve después, el detalle avisa de
cuántas partidas han quedado desfasadas y hay una acción explícita para traer
los precios nuevos.

### Versiones, plantillas e informes (Fase 4)

**Versiones.** Las de un mismo presupuesto se agrupan por `raiz_id`, que en la
primera es nulo. `POST /nueva-version` duplica el árbol entero y la versión
nueva nace en borrador y con los precios sueltos, que es lo que se quiere al
retomar un presupuesto emitido para revisarlo. El código lleva sufijo:
`PRE00001`, `PRE00001.2`.

**Plantillas.** Una plantilla es un presupuesto con `es_plantilla = true`.
Versionar e instanciar una plantilla son la misma operación —copia profunda—,
así que hay un solo motor de copia y no dos caminos que se desincronicen. Por
defecto la plantilla se guarda **sin mediciones**: lo reutilizable es qué
partidas lleva, no cuántos metros medía aquella obra. `tipo_obra` clasifica las
plantillas y es la semilla del histórico para la sugerencia de patrones por IA.

`CAMPOS_COPIABLES` enumera a mano lo que viaja con la copia, en vez de clonar el
objeto entero: añadir una columna obliga a decidir si se copia o no, en lugar de
colarse sin que nadie lo piense. Un test comprueba que todos existen.

**Comparación.** `GET /{a}/comparar/{b}` empareja partidas por capítulo y código
y devuelve altas, bajas, cambios con su delta y el total de idénticas.

### FIEBDC-3 / BC3 (Fase 5)

`fiebdc/` está en cuatro piezas encadenadas: `lector` (bytes a registros),
`parser` (registros a modelo intermedio), `importador` (modelo a base de datos)
y `exportador`. Parsear sin escribir permite el endpoint `/analizar`, que dice
qué trae un fichero antes de tocar nada.

**Codificación.** La declara el propio fichero en `~V`, así que hay que leer ese
registro antes de saber cómo decodificar el resto. Se resuelve leyendo la
cabecera con latin-1 —que nunca falla, porque asigna carácter a los 256 bytes—
y decodificando después con la buena. Sin declaración se asume cp1252, que es lo
que emiten Presto y Arquímedes; suponer UTF-8 destrozaría todas las tildes.

**Clasificación por estructura, no por sufijo.** La raíz (`##`) y los capítulos
(`#`) sí salen del código, que es la parte de la convención que todos respetan.
Para el resto manda quién descompone a quién: sin descomposición es un básico;
con descomposición, unitario si cuelga de un capítulo y auxiliar si solo lo usan
otros precios. Un auxiliar es, por definición, un descompuesto dentro de otro
descompuesto.

**Precios recalculados y discrepancias.** El fichero trae sus precios, pero se
recalculan con nuestras reglas de redondeo y se guarda el resultado. Las
diferencias se listan en vez de tragarse: son la medida de si nuestro modelo
coincide con el del programa que generó el fichero.

**Cálculo en memoria.** Un banco grande trae decenas de miles de conceptos, así
que los precios se resuelven en orden topológico en memoria y se escriben con
inserciones masivas. 10.000 conceptos y 21.000 líneas de descomposición se
importan en unos 2,6 s; con la cascada por SQL serían minutos.

**Tolerancia.** Los registros no interpretados, los campos que faltan y las
fechas ilegibles se anotan como incidencias y no abortan nada. Lo único que sí
detiene la importación son los ciclos en la descomposición, detectados en
memoria antes de escribir: responde 422 y no deja nada a medias.

> **Pendiente de validar contra un BC3 real.** Todo lo anterior está probado
> contra ficheros sintéticos construidos según la norma, no contra un BEDEC ni
> una exportación de Presto. Lo más probable que necesite ajuste: el orden de
> los subcampos de `~M`, el formato de fecha de `~C` y los escapes dentro de los
> textos.

**Informes.** Tres documentos en PDF: presupuesto, estado de mediciones y cuadro
de precios descompuestos. Se componen con Jinja2 (`plantillas/*.html`) y se
rasterizan con WeasyPrint dentro del contenedor, sin servicio externo. Al ser
HTML+CSS, ajustar el papel no obliga a tocar Python. La maqueta es A4 con
cabecera y pie repetidos, encabezados de tabla que se repiten al cortar página y
filas que no se parten.

### Datos

- Cada módulo posee un **schema propio de PostgreSQL** (`core`, `presupuestos`…).
  Su migración lo crea y lo destruye sin tocar a los demás.
- Toda tabla raíz de negocio lleva `organization_id` (`OrganizationMixin`),
  aunque el despliegue sea single-tenant. Es la columna sobre la que se
  apoyarán las políticas RLS en Fase 5.
- La sesión publica la organización activa en la conexión como
  `app.organization_id`, que es lo que leerán esas políticas.

### Migraciones

Una rama de Alembic por módulo, con su propia revisión base y su `branch_label`:

```bash
# aplicar todas las ramas
docker compose run --rm migrate

# nueva migración en un módulo
docker compose run --rm api alembic revision --autogenerate \
  -m "descripción" --branch-label presupuestos \
  --version-path app/modules/presupuestos/migrations
```

`upgrade heads` en plural: con varias ramas, `head` en singular fallaría.

### Autenticación y multi-tenant real (Fase 6)

`AUTH_BACKEND=keycloak` (por defecto) valida el JWT contra el realm `obras`, que
se importa solo al arrancar Keycloak (`keycloak/realm-obras.json`, sin tocar
nada a mano). `AUTH_BACKEND=stub` sigue disponible para pruebas y scripts:
resuelve un `Principal` fijo sin autenticación real. Los dos implementan la
misma interfaz (`AuthBackend`, `Principal`, `get_principal`), así que ningún
módulo de negocio distingue cuál está activo.

**Validación del token.** `KeycloakAuthBackend` comprueba la firma contra las
claves públicas del realm (JWKS, cacheadas en memoria con reintento si el `kid`
no se reconoce — rotación de claves), la audiencia (`obras-api`) y el emisor.
El emisor se acepta en dos variantes: la URL interna (`http://keycloak:8080`,
la que usa la API) y la pública (`http://localhost:8081`, la que ve el
navegador y la que lleva el token) — nunca se llama a Keycloak para validar un
token concreto, eso metería una petición de red en cada request.

**Organización desde el claim.** El atributo de usuario `organizacion` en
Keycloak (mapeado al token vía protocol mapper) dice a qué organizaciones puede
entrar. La cabecera `X-Organization-Slug` conmuta entre ellas; pedir una que no
esté en el token responde `403`, nunca se acepta a ciegas.

**RLS de verdad, no solo filtro de aplicación.** Todas las tablas de negocio
tienen Row Level Security con `FORCE`, sobre la variable de sesión
`app.organization_id` que publica `get_session`. `core.organization` queda
fuera a propósito: hace falta poder leerla para resolver la organización de
quien acaba de autenticarse, antes de que exista contexto.

> ⚠️ **Un superusuario se salta RLS siempre**, sin importar `FORCE ROW LEVEL
> SECURITY` — esa cláusula solo afecta al propietario de la tabla cuando no es
> superusuario. La imagen oficial de Postgres crea `POSTGRES_USER` como
> superusuario, así que si la API se conectara con ese rol, las políticas
> serían papel mojado. Por eso la migración `core_0003` crea `obras_app`
> (`NOSUPERUSER NOBYPASSRLS`) con permisos mínimos, y es el rol con el que se
> conecta el contenedor `api` — `migrate` sigue usando el admin porque las
> migraciones hacen DDL. Se verificó el aislamiento conectando directamente
> como `obras_app`: sin contexto, 0 filas visibles (falla cerrado); una
> organización nunca ve datos de otra; y un intento de `INSERT`/`UPDATE`
> cruzado es rechazado por la política `WITH CHECK`, no simplemente ignorado.

**Login PKCE sin librería.** El frontend implementa el flujo de código con
PKCE en `lib/auth.ts` con `crypto.subtle`, sin ninguna dependencia de OIDC.
Los tokens viven en `sessionStorage` (se borran al cerrar la pestaña) y se
refrescan solos cuando caducan. La configuración pública (`GET /api/config`)
se sirve en tiempo de ejecución, no se compila en el bundle: el mismo build
sirve para desarrollo y producción.

### Gestión de obra (Fase 7)

Dos módulos nuevos: `obras` (ejecución) y `compras` (albaranes), que completan
el grafo de dependencias ya previsto desde la Fase 0.

**Personal → Asignación → ParteTrabajo** replica a propósito el patrón
Concepto → Partida → LineaMedicion del núcleo de precios. `Personal` es la
plantilla propia de la organización (no un tercero: un tercero es una entidad
externa, y la mano de obra subcontratada ya se factura como compra). Una
`Asignacion` copia el `coste_hora` de la ficha en el momento de asignar al
trabajador a una obra —igual que una partida copia el precio de su
concepto—, así que subir el coste de alguien no reescribe en silencio el
histórico de una obra ya cerrada. Un `ParteTrabajo` es el parte diario: horas
reales de un día, con el coste materializado.

**Albarán** registra el material que entra en obra desde un proveedor.
`AlbaranLinea.producto_id` es opcional, como `Partida.concepto_id`: un
material fuera de catálogo se anota a mano sin forzar un alta solo para esa
línea.

**El informe de coste real vs. presupuestado no puede vivir en `obras`.**
Necesita cruzar mano de obra (`obras`), materiales (`compras`) y presupuesto
(`presupuestos`), y la dependencia entre módulos va en un solo sentido:
`compras` depende de `obras`, nunca al revés. Por eso `costes.py` —y su ruta
pública `GET /api/obras/{id}/costes`— vive en el módulo `compras`, aunque la
URL hable de "obras". Cada fila del informe compara cifras **directas** de un
capítulo (sin arrastrar subcapítulos), lo que garantiza que la suma de todas
las filas cuadre siempre con el total sin contar nada dos veces.

> ⚠️ **Un schema nuevo no hereda los permisos de `core_0003`.** Esa migración
> le dio al rol de mínimo privilegio acceso a los cuatro schemas que existían
> en la Fase 6; los de esta fase (`obras`, `compras`) tuvieron que pedirlo
> explícitamente con `conceder_privilegios_app()` (ahora en `app/core/rls.py`)
> en su propia migración, o la primera consulta fallaba con *"permission
> denied for schema"*. Cualquier módulo futuro que abra un schema nuevo tiene
> que hacer lo mismo.
>
> Al generar estas migraciones también salió a la luz un efecto colateral de
> nombrar el schema de este módulo igual que el rol admin (`obras` = `obras`):
> `search_path = "$user", public` metía el schema en la ruta de búsqueda nada
> más conectar, y como SQLAlchemy cachea `default_schema_name` en el primer
> connect, autogenerate confundía el schema propio con el de por defecto y
> proponía desfases que no existían. Se resolvió fijando `search_path` en el
> propio connect de Alembic (`connect_args={"server_settings": ...}`), no con
> un `SET` a mitad de sesión — para entonces SQLAlchemy ya había cacheado el
> valor viejo.

### Certificaciones, facturación y cobro (Fase 8)

Módulo `facturacion`, el último del grafo de dependencias inicial:
`Certificacion` (medición acumulada de obra ejecutada) → `Factura` (documento
fiscal, generado desde una certificación o suelta) → `Cobro` (ingresos reales,
uno o varios por factura).

**Certificación.** `CertificacionLinea` copia código, resumen, unidad y precio
de la partida en el momento de certificar —el mismo motivo por el que
`Partida` copia del `Concepto`—, y guarda `medicion_anterior` (la acumulada en
la última certificación de esa partida en esa obra, 0 si es la primera),
`medicion_actual` (lo que se pide certificar) y `medicion_periodo` como
diferencia. Una certificación se bloquea al emitirse: facturar sobre una que
todavía puede cambiar de importe dejaría un número fiscal correteando detrás
de un dato inestable. La retención de garantía es opcional (0 % por defecto,
no todo el mundo la aplica) y se calcula sobre el importe ejecutado del
periodo, nunca acumulado.

> ⚠️ **Numeración fiscal, la pieza que no admite descuido.** `Factura.numero`
> se queda a `NULL` mientras es borrador —descartar un borrador nunca deja un
> hueco en la serie— y se asigna solo al emitir, como `MAX(numero) + 1` de esa
> serie **incluyendo las anuladas** (nunca se reutiliza un número, aunque la
> factura que lo llevaba se haya anulado). Una factura emitida no se puede
> borrar ni editar: solo anular, conservando su fila y su número. Verificado
> con datos reales: FAC00001 salió con `2026/1`; al anularla y generar una
> factura nueva desde la misma certificación, la siguiente emisión salió con
> `2026/2`, no `2026/1`.

**El webhook a n8n es best-effort a propósito.** El estado fiscal de la
factura (emitida, numerada) no depende de que n8n esté disponible en ese
instante — si el aviso falla, `notificado_n8n_en` se queda a `NULL` y hay una
acción explícita («Reintentar envío») para repetirlo. Este módulo no genera
Facturae ni habla con la AEAT: eso exige certificado digital y registro
previo, y es tarea del flujo de n8n que el propio despliegue configure. Lo que
se publica es un payload con lo necesario (NIF emisor/receptor, serie,
número, importes, IVA) para que ese flujo exista.

**Situación de cobro y "vencida" son derivadas, no almacenadas** —mismo
principio que `clase` en el concepto o los totales del presupuesto—:
`situacion_cobro()` compara la suma de `Cobro.importe` contra `Factura.total`
en cada lectura, así que nunca puede desincronizarse de la realidad.

### IA — patrones de presupuesto (Fase 9)

Módulo `ia`, opt-in y separado del resto: una organización puede no querer
activarlo (coste de API, o simplemente no querer usar IA), y desactivado
responde 404 como cualquier otro módulo. DeepSeek es el proveedor de IA fijo
de todo este stack (`app/core/config.py`: `DEEPSEEK_API_KEY`,
`DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`); sin clave configurada, pedir una
sugerencia responde `503` en vez de fallar a medias.

**Dos piezas separadas a propósito.** `estadisticas.py` es autoalojado y no
llama a ningún modelo: agrega, por tipo de obra, qué capítulos (por resumen
normalizado) y qué partidas (por `concepto_id`) aparecen con más frecuencia
en el histórico propio de presupuestos y plantillas. Si no hay histórico de
ese tipo de obra concreto, cae a mirar todos los presupuestos de la
organización (`generico=true` en la respuesta) en vez de no proponer nada.
Esto es útil por sí solo, sin IA, y es el terreno firme sobre el que
`deepseek.py` pide una síntesis.

> 🔒 **Privacidad por diseño: nunca precios, nunca datos de cliente.** Lo
> único que sale hacia DeepSeek es vocabulario estructural — tipo de obra,
> descripción libre, y resúmenes/unidades/códigos de los capítulos y
> partidas más frecuentes. El cuadro de precios de una constructora es
> información competitiva; a la IA solo se le pregunta "qué suele ir junto
> en este tipo de obra", nunca "cuánto cuesta". `SugerenciaPatron` guarda
> `estadisticas_enviadas` tal cual viajaron, para poder auditarlo.

**Resolución contra el catálogo propio.** DeepSeek responde en JSON
(`response_format: json_object`) con capítulos y partidas, cada partida con
un `codigo_existente` opcional. `service._resolver_partidas` cruza ese
código contra `Concepto` de la organización: si existe, prevalecen los
datos *reales* del concepto (nunca lo que el modelo repite); si no existe —ya
sea porque el modelo propone algo nuevo o porque alucina un código— se trata
como partida nueva, sin precio.

**Nada se escribe hasta que el usuario lo confirma.** `solicitar_sugerencia`
solo persiste la propuesta (`SugerenciaPatron`, con `plantilla_id = NULL`).
El frontend permite revisar y editar resúmenes/unidades y quitar líneas antes
de aceptar. Solo al confirmar, `crear_plantilla_desde_sugerencia` escribe: por
cada partida sin concepto real se crea un `Concepto` nuevo (`unitario`,
`precio = 0,00`, `origen_dato = ia`) que entra sin tarifar en el cuadro de
precios —así el catálogo crece con el uso, pero cualquiera que lo vea después
sabe que está pendiente de revisar—, y el conjunto se guarda como
`Presupuesto` con `es_plantilla=true` y `origen_dato=ia`. Una sugerencia solo
genera una plantilla una vez (`409` si se intenta dos veces sobre la misma).

Verificado con una llamada real a DeepSeek: pedida una sugerencia para
"rehabilitación de fachada", propuso reutilizar tres unitarios ya existentes
del histórico (por código) y dos partidas nuevas ("ventana de aluminio con
rotura de puente térmico", "puerta de entrada de seguridad"); al aceptarla,
ambas quedaron creadas en `presupuestos.concepto` con `precio = 0.00` y
`origen_dato = ia`, y la plantilla resultante quedó enlazada en
`sugerencia_patron.plantilla_id`.

### IA — medición desde planos (Fase 10)

Primer slice del componente de mayor incertidumbre técnica del proyecto:
leer un plano acotado (imagen o PDF) y proponer líneas de medición para una
partida ya existente. Queda pendiente, para una fase posterior, la otra
mitad de la visión original —estimar medidas desde foto/vídeo de obra
ejecutada, bastante menos fiable al no tener cotas ya impresas de las que
partir—.

**Gemini, no DeepSeek, y solo para esto.** Decisión del usuario: todo lo que
sea visión/imagen va contra Gemini (`app/modules/ia/gemini.py`); DeepSeek
sigue siendo el proveedor para lo que es texto/estructura (Fase 9). A
diferencia de la sugerencia de patrones, aquí no hay forma de evitar que
salga información sensible hacia fuera: el fichero del plano entero viaja al
proveedor, porque leerlo es la tarea en sí. Por eso sigue siendo el usuario
quien decide subir cada plano, uno a uno, no un proceso que analiza en lote.

**Mismo idioma que Fase 9: nada se escribe hasta confirmar.** `POST
/api/ia/mediciones` (multipart: `partida_id` + fichero) llama a Gemini y solo
persiste la propuesta en `LecturaPlano` (auditoría: fichero, modelo,
respuesta cruda, `observaciones` de lo que Gemini no pudo interpretar con
confianza). El usuario revisa y edita las líneas en el frontend —puede
excluir cualquiera— antes de `POST /api/ia/mediciones/{id}/aplicar`, que es
la única función que escribe: reutiliza
`presupuestos_service.crear_linea()` línea a línea, así que el recálculo de
la partida es exactamente el mismo que al añadir una línea a mano. Una
lectura solo se aplica una vez (`aplicada_en` pasa de `NULL` a la fecha;
reintentarlo da 409), mismo idioma que `SugerenciaPatron.plantilla_id`.

**El parcial nunca sale del LLM.** Gemini solo propone `comentario`, `uds`,
`longitud`, `anchura` y `altura` por línea — el parcial que se le muestra al
usuario para revisar, y el que de verdad se guarda al aplicar, se calcula
siempre en el servidor con `presupuesto_calculo.parcial_de()`, la misma
función que usa cualquier línea de medición tecleada a mano.

Verificado con una llamada real a Gemini sobre un plano de planta acotado:
identificó correctamente la fachada principal (12,60 m de longitud, 2,50 m
de altura, tomado del alzado) y dedujo los muros longitudinales y
transversales de dos dormitorios acotados en planta, aplicando la altura del
alzado a cada uno y señalando en `observaciones` los supuestos que había
tenido que asumir (grosor de muros y huecos no acotados en el plano). Al
aplicar una selección de esas líneas, la partida recalculó su medición e
importe correctamente, y un segundo intento de aplicar la misma lectura
devolvió 409 tal como se esperaba.

### Administración de organizaciones (Fase 11)

El modelo de datos es multi-tenant desde el primer día (`organization_id` en
toda tabla de negocio, RLS desde la Fase 6), pero hasta esta fase no existía
ninguna pantalla ni endpoint para gestionar los tenants en sí: crear uno
nuevo exigía un `INSERT` a mano en la base de datos. Esta fase cierra ese
hueco con un panel de administración.

**Mismo login que cualquier usuario de un tenant — a propósito.** No hay un
portal de administración aparte ni un mecanismo de autenticación distinto:
`superadmin` es un rol de Keycloak más. Quien lo tiene entra por la pantalla
de siempre, aterriza en su organización de siempre (`dev` sigue siendo un
usuario normal de `demo`), y lo único que cambia es que el shell le añade una
sección "Administración" — igual que el rol `admin` ya hacía aparecer un
badge en la topbar. `require_superadmin` (`app/core/auth.py`) es la única
pieza nueva de autenticación: una guarda de router que exige el rol además de
estar autenticado, nada más.

**Qué gestiona y qué no.** El panel cubre organizaciones (crear, editar
nombre/CIF, activar/desactivar) y, para cualquier organización, qué módulos
tiene encendidos — la misma pantalla de Ajustes que ya existía, pero
operable sobre cualquier tenant, no solo el propio. Deliberadamente NO
permite navegar los datos de negocio de un tenant (sus presupuestos, sus
terceros...): eso seguiría exigiendo cruzar RLS tabla por tabla y es un salto
de alcance que nadie ha pedido todavía.

El resto de esta fase (ver más abajo) amplía el panel con tarifas y
descuentos, cobros y uso de IA por organización, alta de usuarios de
organización con correo real, y ajustes globales de IA/SMTP/pasarela de pago
— todo detrás de la misma guarda `require_superadmin`.

> ⚠️ **Hallazgo real durante la verificación, no anticipado en el diseño**:
> `core.organization` no lleva RLS (a propósito, hay que poder leerla antes
> de que exista contexto de organización), pero `core.organization_module`
> **sí** la lleva desde `core_0002` — cosa que pasé por alto al diseñar esta
> fase. El primer intento de activar un módulo para un tenant que no era el
> del propio superadmin falló con "new row violates row-level security
> policy": la sesión seguía llevando el `app.organization_id` del
> superadmin, no el del tenant que se quería administrar. Solución:
> `fijar_organizacion_activa()` (`app/core/database.py`), que hace
> `set_config('app.organization_id', ..., true)` — local a la transacción,
> igual que hace `get_session()` al principio de cada request — justo antes
> de tocar `organization_module` para un tenant ajeno. Verificado que no hay
> fuga entre tenants: tras activar módulos para uno nuevo, los del resto
> quedaron exactamente como estaban.
>
> Este es el motivo, además, de que el panel no navegue datos de negocio de
> un tenant: cada tabla de negocio tendría que pasar por el mismo mecanismo
> tabla a tabla, y es justo el tipo de superficie que conviene ampliar solo
> cuando haga falta de verdad, no por adelantado.

Verificado en vivo: creada la organización `obra-verde` desde el panel,
apareció con solo el módulo `core` activo (el estado por defecto correcto);
activar `presupuestos` arrastró sus dependencias (`catalogo`, `terceros`)
igual que en Ajustes; un slug repetido devolvió 409; y una petición sin el
rol `superadmin` devolvió 403.

### Tarifas, cobros, uso de IA y ajustes globales (ampliación de la Fase 11)

Cuatro piezas nuevas, todas detrás de `require_superadmin`, todas en el
schema `core` (mismo motivo que `organization`/`organization_module`: son
administrativas, no de negocio de un tenant, así que ninguna lleva RLS
—verificado con `pg_policies`, no solo mirando la migración que las creó,
lección de esta misma fase—):

**Tarifas y descuentos.** `Tarifa` fija un precio mensual por módulo
(`TarifaModulo`) y un precio por cada 1000 tokens de IA, por proveedor
(DeepSeek y Gemini no cuestan lo mismo). `Descuento` cuelga de una tarifa
entera (promoción general) o de una organización concreta (trato
particular) — nunca de las dos a la vez, y un descuento porcentual no puede
superar el 100 %; ambas reglas se comprueban en el servicio antes de tocar
la base. Puede ser `porcentaje` o `importe_fijo`, y tener vigencia temporal
(`vigente_desde`/`vigente_hasta`, ambas opcionales). El coste estimado del
mes (`GET /organizaciones/{id}/coste-estimado`) aplica primero todos los
porcentuales vigentes en cadena y luego los de importe fijo, sin bajar de
cero — es una decisión de orden entre varias razonables, documentada en
`calcular_coste_mensual`, no la única posible.

**Medición de uso de IA por organización y usuario.** Cada llamada real a
DeepSeek o Gemini deja una fila en `UsoIA` (organización, usuario de
Keycloak, proveedor, modelo, tokens de entrada/salida, referencia a la
sugerencia o lectura que la disparó). Las claves de IA son **compartidas**:
la plataforma paga un único consumo con la clave de `Ajustes IA` y se lo
repercute a cada organización por su tarifa — ninguna organización trae la
suya (decisión explícita del usuario). `app/modules/ia/credenciales.py`
resuelve la clave/modelo efectivos con BD primero y `.env` como respaldo, así
que cambiar la clave desde el panel no exige tocar contenedores; verificado
en vivo con llamadas reales (una sugerencia de patrón con DeepSeek: 620
tokens de entrada / 316 de salida; una lectura de plano con Gemini: 1370/373)
y confirmando que aparecen tal cual en `uso_ia` y en el coste estimado.

**Cobros de la plataforma a un tenant** (`CobroSaas`) se registran a mano
por ahora (`origen='manual'`); `referencia_externa` es el hueco donde
encajará el webhook de Paddle cuando se conecte de verdad — decisión
explícita del usuario: por ahora solo se prepara el modelo de datos, sin
llamar a la API real de Paddle.

**Alta de administrador de organización, con correo real.** Decisión
explícita del usuario: nada de mostrar la contraseña una vez en pantalla,
correo de verdad. `app/core/keycloak_admin.py` es la primera vez que el
backend llama al **API de administración** de Keycloak (no solo valida
tokens): crea el usuario en el realm con una contraseña temporal
(`requiredActions: UPDATE_PASSWORD`, la cambia en el primer login), le
asigna los roles `admin`/`usuario`, y `app/core/mailer.py` +
`plantillas/bienvenida.html` envían el correo con el SMTP propio de la
plataforma (`Ajustes → SMTP`, distinto del SMTP que cada organización puede
configurar para SU propio correo saliente). Si el correo falla, el usuario
ya existe igualmente en Keycloak — "reenviar invitación" no repite la
contraseña anterior (nunca se guarda en la base), genera una nueva y la
sustituye en Keycloak antes de reintentar el envío.

> ⚠️ **Hallazgo real durante la verificación, no anticipado**: el primer
> usuario creado por la API perdió silenciosamente el atributo
> `organizacion` — Keycloak 26 valida las peticiones del API de
> administración contra el **User Profile** del realm, y cualquier atributo
> no declarado ahí se descarta sin avisar. El atributo `organizacion` solo
> existía de facto porque `dev` se creó por *import* del realm al arrancar
> (que no pasa por esa validación), no porque estuviera declarado. Se
> corrigió declarando `organizacion` en el User Profile (en caliente, vía
> `PUT /admin/realms/obras/users/profile`, y en `realm-obras.json` para que
> un despliegue nuevo lo traiga de serie) — verificado creando un segundo
> usuario y confirmando que el atributo esta vez sí persiste.

**Motivo del descuento.** Añadido a petición del usuario: `Descuento.motivo`
(`primer_mes_gratis`, `fidelizacion`, `retencion`, `campana`,
`aumento_modulos`, `otro`) clasifica *por qué* se dio el descuento, sin
cambiar cómo se calcula — eso lo siguen decidiendo `tipo`/`valor`/vigencia.
Es deliberadamente solo una etiqueta de reporting, no un tipo de descuento
con comportamiento propio: "primer mes gratis" se sigue creando como
cualquier otro (100 % con `vigente_hasta` puesto a mano), no se calcula solo
a partir de la fecha de alta de la organización — decisión explícita del
usuario para no automatizar de más en esta pasada. Verificado en vivo
combinando dos descuentos activos a la vez sobre `obra-verde` (100 % +
20 %, aplicados en cadena): el total bajó a 0,00 € y
`descuentos_aplicados` reflejó correctamente la diferencia.

**Descuentos como catálogo reutilizable, no como filas exclusivas.**
Rediseñado a petición del usuario tras usar la primera versión: un
`Descuento` ya no pertenece en exclusiva a una tarifa o a una organización —
se crea una vez (en Tarifas) y se **aplica** a cualquier número de
organizaciones. `OrganizacionDescuento` es la tabla de aplicación: quién lo
tiene, desde cuándo (`aplicado_en`) y si se ha anulado (`anulado_en`, NULL
mientras sigue en vigor — mismo idioma que `Factura.numero`). Anular no
borra la fila: es el histórico. Volver a aplicar el mismo descuento tras
anularlo crea una fila nueva, no reutiliza la anterior. Desde la ficha de
una organización ya no se **crean** descuentos, solo se buscan (por nombre)
y se aplican en bloque, o se anula el que esté vigente — coherente con que
el catálogo vive únicamente en Tarifas.

**Gestión de descuentos en el frontend, en dos pantallas con roles
distintos.** En Tarifas, `DescuentosCard.tsx` es el catálogo: crear, editar,
activar/desactivar, siempre visible bajo la tabla de tarifas (no escondido
en un modal, corregido tras el primer intento). En la ficha de una
organización, `AplicacionesDescuentoCard.tsx` es donde se aplica: un buscador
por nombre sobre el catálogo (excluyendo lo que ya esté vigente), selección
múltiple con checkboxes, un botón "Aplicar", y la tabla de histórico con
"Anular" sobre lo vigente — sin formulario de creación. Verificado en vivo:
crear "SUMMER 2026" (15 %) en el catálogo, aplicarlo a `obra-verde` (coste
20,00 €→17,00 €), reaplicarlo sin anular antes (409), anularlo (coste vuelve
a 20,00 €, la fila del histórico se conserva con su `anulado_en`), y
reaplicarlo de nuevo (fila nueva, no reutiliza la anulada).

**Ajustes globales de IA no son las únicas nuevas**: `Ajustes → SMTP`
(correo propio de la plataforma) y `Ajustes → Pasarela de pago` (Paddle,
solo credenciales por ahora) completan el bloque. Las tres son tablas de una
sola fila (`id` fijo a 1): "obtener" crea la fila con valores por defecto si
no existe todavía, así el resto del código nunca distingue entre "no
configurado" y "no existe la fila". Ninguna devuelve la clave/contraseña real
en un `GET` — solo un booleano "configurada" — para que ni siquiera una
pantalla de superadmin exponga secretos de vuelta al navegador.

### Usuarios, grupos y permisos por módulo (Fase 12)

Hasta esta fase, dentro de una organización todo el mundo con el rol `admin`
veía y editaba todo, y quien no lo tenía no entraba en la aplicación en
absoluto — no había término medio. Esta fase lo resuelve con grupos: cada
grupo da, por módulo, un alcance de **ver** y otro de **editar**, cada uno en
tres niveles (`ninguno` < `propios` < `todos`), y un usuario puede
pertenecer a varios grupos — pertenecer a más nunca resta, solo puede
ampliar (se toma el alcance más amplio de cada módulo entre todos sus
grupos). El rol `admin` de Keycloak (existe desde la Fase 6) sigue siendo un
atajo: quien lo tiene tiene `todos`/`todos` en todo sin depender de ningún
grupo — pensado para quien deba tener acceso total sin gestión fina, como el
primer usuario de una organización nueva. Los usuarios creados desde ahora
**no** reciben `admin` por defecto, solo el rol mínimo `usuario`; hay que
marcarlo explícitamente al crearlos, o añadirlos a grupos después.

**De dónde sale "propios".** Se añadió `AutoriaMixin`
(`creado_por_subject`/`creado_por_nombre`) a los 13 tipos de entidad raíz de
todos los módulos de negocio (`Tercero`, `Contacto`, `Producto`, `Familia`,
`Concepto`, `Presupuesto`, `Obra`, `Personal`, `Albaran`, `Certificacion`,
`Factura`, `SugerenciaPatron`, `LecturaPlano`) — nunca a las líneas hijas
(`Descomposicion`, `Capitulo`, `Partida`, `LineaMedicion`, `AlbaranLinea`,
`CertificacionLinea`, `Asignacion`, `ParteTrabajo`, `PrecioSuministro`,
`Cobro`), que heredan la visibilidad de su padre en vez de llevar su propio
`creado_por`: una partida es "propia" si el presupuesto que la contiene lo
es, no por sí misma. Todas las columnas son nullable a propósito — un
registro anterior a esta fase no tiene autor conocido, y queda invisible
bajo alcance `propios`; es el comportamiento esperado, no un defecto que
haya que corregir con una migración de datos. Quién es "quien crea" se
resuelve con un `ContextVar` nuevo (`current_principal()`,
`app/core/tenancy.py`, mismo patrón que ya existía para
`current_organization_id()`) en vez de pasar el `principal` como parámetro
por las ~15 funciones `crear_X` de cada servicio; `datos_autoria()` lo
resume a un `dict` para pasar por `**` al construir cada fila.

**Motor de permisos** (`app/core/permisos.py`): `permiso_efectivo(session,
principal, module_code)` resuelve el alcance agregando `GrupoPermiso` de
todos los grupos del usuario en esa organización (o el atajo de `admin`), y
`require_permiso(module_code, accion)` es una dependencia de FastAPI que
403 si el alcance es `ninguno` y si no, devuelve el alcance concedido para
que el endpoint sepa si tiene que filtrar. El patrón se repite igual en las
~40 rutas de los 7 módulos de negocio: `ver` filtra el listado por
`creado_por_subject` cuando el alcance es `propios`; el detalle/edición/
borrado de un registro concreto comprueban la propiedad con
`verificar_propiedad()` y devuelven **404, no 403** si no es suyo — mismo
principio de "fallar cerrado" sin revelar que el registro existe que ya
usa RLS entre organizaciones. Para las entidades hijas, la comprobación
sube hasta el padre (p. ej. `_partida_propia` en `presupuestos` resuelve el
`Presupuesto` dueño antes de dejar tocar sus líneas de medición).

**Grupos y usuarios se gestionan en dos sitios con el mismo contrato.**
`Grupo`/`GrupoPermiso`/`GrupoUsuario` (`app/modules/core/permisos_models.py`)
sí llevan RLS —a diferencia de `Tarifa`/`Descuento`, aquí el autoservicio del
propio tenant también toca estas tablas, no solo el superadmin—, verificado
con `pg_class`/`pg_policies`, no solo mirando la migración que las creó
(lección de la Fase 11, aplicada esta vez desde el principio).
`permisos_router.py` expone el mismo CRUD de grupos y usuarios dos veces:
`router` bajo `/api/admin/organizaciones/{id}/...` (superadmin, cualquier
organización, `fijar_organizacion_activa()` antes de tocar las tablas con
RLS) y `tenant_router` bajo `/api/...` (autoservicio, la propia organización,
gated por el nuevo `require_admin_organizacion` en vez de
`require_superadmin`). El frontend comparte un único componente,
`UsuariosYGruposCard.tsx`, parametrizado por un objeto `UsuariosGruposAPI`
que solo cambia a qué URL apuntan sus funciones — `AdminOrganizacionDetalle`
lo monta con `api.admin.organizaciones.usuariosYGrupos(id)`, la pantalla
nueva `/usuarios-grupos` (visible en el menú solo con rol `admin`) con
`api.usuariosYGrupos`.

**Los usuarios de Keycloak no tienen tabla propia**, igual que en la Fase
11: `KeycloakAdminClient` ganó `listar_usuarios`/`actualizar_usuario`/
`eliminar_usuario`, y una comprobación nueva,
`pertenece_a_organizacion()`, evita que el autoservicio de un tenant edite o
borre un usuario de **otra** organización adivinando su id de Keycloak — el
API de administración de Keycloak no filtra eso por sí solo, así que sin
esa comprobación el aislamiento entre organizaciones se rompería justo en
este único punto donde el backend sale de RLS.

> ⚠️ **Bug real encontrado en la verificación, no en el diseño**:
> `permiso_efectivo` leía la organización desde `require_organization_id()`
> (el `ContextVar` de tenancy) en vez de usar `principal.organization_id`,
> el parámetro que la propia función ya recibía. Inofensivo en una request
> real —el middleware fija los dos a la vez—, pero una redundancia sin
> sentido que además rompía cualquier llamada directa a la función fuera de
> una request (el primer script de verificación falló con "No hay
> organización activa en el contexto"). Corregido para usar el parámetro
> directamente; ahora la función es pura respecto a sus argumentos y no
> depende de contexto ambiental oculto.

Verificado en vivo contra la base real (no mockeada): un grupo con alcance
`propios` en `terceros`, dos usuarios distintos creando cada uno un
`Tercero`, confirmando que cada uno solo ve el suyo en el listado filtrado y
que ambos aparecen sin filtro; el atajo de `admin` dando `todos`/`todos` sin
pertenecer a ningún grupo; y el mismo patrón de autoría +
filtrado repetido con éxito en `catalogo` (`Producto`), `presupuestos`
(`Concepto` y `Presupuesto`, incluida la cadena `Presupuesto → Capitulo`), y
cruzando `obras`/`compras`/`facturacion` (`Obra`, `Personal`, `Albaran`,
`Factura` creados por el mismo usuario y con `creado_por_subject` correcto
en los cuatro). `alembic check` sin desviación y los 155 tests existentes en
verde tras cada uno de los 7 módulos tocados.

## Tests

```bash
docker compose run --rm api pytest
```
