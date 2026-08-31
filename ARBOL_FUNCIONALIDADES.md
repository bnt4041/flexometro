# Árbol de funcionalidades — Flexómetro

Índice de todo lo que hace la aplicación, por área. Para el detalle técnico
de cada pieza (arquitectura, decisiones, por qué se hizo así) está
[README.md](README.md); esto es el mapa para organizarse, no la
documentación técnica.

> Generado a partir del registro real de módulos de la aplicación
> (`backend/app/modules/*/ __init__.py`, `ModuleSpec`), no de memoria —
> así que si un nombre o una ruta cambian, este documento se queda
> desactualizado y toca regenerarlo, no fiarse de él a ciegas.

---

## 01 · Plataforma

*Ruta: `/ajustes`, `/admin/*` — módulo `core`*

Organizaciones, activación de módulos e identidad. No es un módulo de
negocio: es lo que sostiene a todos los demás.

- **Cuentas y organizaciones** — una `Cuenta` agrupa varias organizaciones
  (varios CIF) bajo un mismo contrato de facturación.
- **Multi-tenant real** — Row-Level Security forzado en PostgreSQL sobre
  todas las tablas de negocio, no solo en la aplicación.
- **Autenticación** — Keycloak con JWT + PKCE; rol de base de datos de
  mínimo privilegio.
- **Módulos activables** — cada organización enciende y apaga módulos; el
  conjunto activo se cierra solo bajo dependencias.
- **Permisos** — cuatro acciones (ver, editar, crear, borrar) por módulo,
  cada una con alcance «todos» o «solo los míos».
- **Ajustes de organización** — empresa y logo, bancos y cajas, diccionario
  de referencia, traducción de la interfaz, campos libres, monedas.
- **Numeración de documentos** — patrones configurables por cuenta, con
  secuencia compartida.
- **Administración de la plataforma** — cuentas, tarifas por módulo,
  personal de plataforma (superadmin sin organización propia), ajustes
  globales.
- **Auditoría** — registro de cambios por fila y usuario.
- **Instalable (PWA)** — manifest y service worker; lo ya cargado sigue
  disponible sin conexión.
- **Menú de usuario** — favoritos, ficha de perfil, salir.

## 02 · Terceros

*Ruta: `/terceros`, `/contactos` — módulo `terceros`*

Clientes, proveedores, subcontratistas y contactos. Una sola ficha con
roles, no entidades separadas.

- **Ficha única** — un tercero puede ser cliente, proveedor y
  subcontratista a la vez.
- **Contactos** — personas asociadas a un tercero, con su propio email y
  teléfono.
- **Compartidos** — el mismo maestro se puede usar entre organizaciones de
  una misma cuenta, sin duplicarlo.

## 03 · Presupuestos

*Ruta: `/banco-precios`, `/presupuestos` — módulo `presupuestos`*

Banco de precios, mediciones y presupuestos por capítulos. Núcleo del
negocio.

- **Banco de precios** — capítulos, partidas y descompuestos reutilizables
  entre presupuestos.
- **Sistema clásico español** — de precio de suministro a precio unitario,
  con mediciones por capítulo.
- **Versionado** — cada revisión enlazada a su origen; comparar dos
  versiones muestra el delta partida a partida.
- **Plantillas** — un presupuesto se guarda como plantilla y se parte de
  ahí la próxima vez.
- **Exportación** — a plantilla Word propia de la cuenta, y a Excel.
- **FIEBDC-3 / BC3** — importa bancos de precios en el estándar del
  sector.

## 04 · Obras

*Ruta: `/obras`, `/personal` — módulo `obras`*

Ejecución de un presupuesto aceptado: personal asignado, coste real frente
a presupuestado.

- **Ejecución** — arranca de un presupuesto aceptado; controla estado y
  fechas.
- **Personal** — asignación de personal a la obra, con su PRL al día.
- **Coste real** — compras y albaranes imputados frente a lo
  presupuestado, obra a obra.

## 05 · Planos

*Ruta: `/planos` — módulo `planos`*

Biblioteca de planos por obra o presupuesto, calibrables y con medición
encima — sin un solo píxel estimado en DXF.

- **Biblioteca** — un plano cuelga de una obra, de un presupuesto, de los
  dos o de ninguno.
- **Calibración** — sobre una cota conocida en PDF o imagen; exacta desde
  la escala del cajetín en un PDF, o desde las unidades del propio fichero
  en DXF.
- **Capas y anotaciones** — visibles y bloqueables, con notas y líneas
  auxiliares que no miden.
- **Medición** — longitud, área y conteo. En DXF, pinchando la entidad
  real: no se estima dónde está la pared, se sabe.
- **Importación DXF** — capas y unidades del propio fichero; bloques
  explotados con herencia de capa.
- **Lectura con IA** — lee la escala impresa y las cotas escritas de un
  PDF; nunca le pide coordenadas al modelo.
- **A la partida** — lo medido se lleva a una línea de medición real,
  comprobando antes que la unidad encaja.

## 06 · Compras

*Ruta: `/pedidos`, `/albaranes`, `/facturas-recibidas` — módulo `compras`*

Proveedores, pedidos y albaranes de material.

- **Pedidos y albaranes** — a proveedor, con sus líneas y su estado.
- **Facturas recibidas** — de proveedor, con sus propias partidas.
- **Presupuestos de proveedor** — solicitud de precios a varios
  proveedores para un mismo paquete.

## 07 · Clientes / Facturación

*Ruta: `/certificaciones`, `/facturas` — módulo `facturacion`*

Certificaciones de obra, facturas y cobros. Veri\*Factu / Facturae se
integran vía n8n.

- **Certificaciones** — periódicas, sobre lo ejecutado de la obra.
- **Facturas** — emitidas a partir de una certificación o directas.
- **Cobro** — vencimientos y su seguimiento.
- **Veri\*Factu / Facturae** — envío vía integración con n8n.

## 08 · Contratos

*Ruta: `/contratos` — módulo `contratos`*

Formaliza el acuerdo de una obra: con el cliente o con un proveedor.

- **Con el cliente** — formaliza el presupuesto aceptado.
- **Con el proveedor** — formaliza un pedido o una condición marco.

## 09 · PRL y recursos

*Ruta: `/prl`, `/recursos`, `/firmas` — módulo `prl`*

Prevención de riesgos laborales y recursos de la empresa: vehículos y
maquinaria, caducidades, plantillas y firma a terceros.

- **Recursos** — vehículos y maquinaria de la empresa, con su
  documentación.
- **Caducidades** — de toda la documentación PRL —empresa, personal, obra
  y proveedores— en un solo sitio.
- **Plantillas de documento** — con marcadores que se rellenan solos.
- **Firma electrónica** — multifirma con 2FA por un canal distinto al del
  enlace, sello y evidencias; si la firma queda parcial, avisa a quien ya
  firmó.

## 10 · IA — patrones de presupuesto

*Ruta: `/ia/patrones` — módulo `ia`*

Sugiere la estructura de un presupuesto nuevo a partir del histórico
propio, vía DeepSeek.

- **Sugerencia de estructura** — capítulos y partidas típicos de un tipo
  de obra, a partir de lo ya presupuestado.
- **Opt-in** — solo sale del servidor el vocabulario de partidas —nunca
  los precios— y hay que activarlo a propósito.

## 11 · Copiloto

*Widget global — vive dentro del módulo `ia`*

Chat que acompaña a toda la aplicación: busca, resume, explica y propone —
nunca escribe por su cuenta.

- **Chat en toda la aplicación** — busca datos de la organización, los
  resume, explica cómo se hace algo.
- **Herramientas por permiso** — a quien no ve facturas no se le ofrece ni
  la herramienta de buscarlas: no existe, no es que esté cerrada.
- **Nunca escribe solo** — toda propuesta de escritura vuelve con sus
  campos a la vista; confirmar revalida el permiso desde cero.
- **Se apoya en la wiki** — busca en Soporte antes de explicar un
  procedimiento, y lo dice si no lo encuentra.

## 12 · Notificaciones

*Configuración: ficha de usuario / grupo — módulo `notificaciones`*

Avisos configurables: qué recibe cada persona o grupo y por dónde.

- **Por persona o grupo** — se configura desde la propia ficha del
  usuario o del grupo, no en una pantalla aparte.
- **Tres canales** — campana, correo, WhatsApp.
- **Vigilancias** — avisos periódicos: una obra parada demasiado tiempo,
  un documento a punto de caducar.

## 13 · Desarrolladores

*Ruta: `/desarrolladores` — módulo `desarrolladores`*

La puerta para integrar Flexómetro con otros sistemas.

- **Claves de API** — con los mismos ámbitos que los permisos de una
  persona.
- **Webhooks** — firmados, con reintentos y registro de cada envío.

## 14 · Automatizaciones

*Ruta: `/automatizaciones` — módulo `automatizaciones`*

Flujos de nodos que se disparan solos, al estilo n8n.

- **Flujos de nodos** — disparador (evento, URL o reloj) más acciones
  encadenadas que deciden por qué rama sigue el flujo.
- **A prueba de fallos** — un fallo a mitad de camino no borra lo ya
  hecho: queda «parcial», no «fallida».
- **Con guardas** — nada de `eval()`; el nodo HTTP no alcanza la red
  interna; un ciclo siempre termina.

## 15 · Importador

*Ruta: `/importador` — módulo `importador`*

Trae datos de otro sistema desde una hoja de CSV o Excel.

- **Destinos** — terceros, contactos y personal, por el mismo servicio
  que usa la pantalla.
- **Mapeo asistido** — propone qué columna es cada campo antes de
  importar nada.
- **Fila a fila** — si una fila falla, las demás entran igual, y se dice
  cuál y por qué.

## 16 · Informes

*Ruta: `/informes` — módulo `informes`*

Informes agregados sobre los datos de la organización.

- **Agregados** — agrupar por lo que sea, contar o sumar.
- **Con el permiso de quien mira** — un mismo informe da cifras distintas
  a dos personas si su alcance de permiso es distinto.

## 17 · Soporte

*Ruta: `/soporte` — módulo `soporte`*

Tickets para pedir ayuda y una wiki que se entiende por significado, no
por palabra exacta.

- **Tickets** — los abre cualquiera, sin permiso de módulo.
- **Wiki** — indexada por significado (pgvector + embeddings de Gemini):
  «no encuentro el proyecto» encuentra la página que dice «obra».
- **Base del copiloto** — es lo que el asistente lee para responder «cómo
  se hace X», y admite cuando la wiki no lo dice.

## 18 · Transversales

*Sin menú propio — pestañas de cada ficha: módulos `crm`, `documentos`,
`campos_libres`*

Sin menú propio: viven como pestañas dentro de la ficha de cualquier
objeto que las use.

- **CRM** — notas de seguimiento sobre terceros, presupuestos, obras,
  certificaciones y facturas.
- **Documentos** — ficheros adjuntos por ficha, guardados en el almacén de
  objetos.
- **Campos libres** — campos propios definidos por la organización sobre
  terceros, productos, obras y presupuestos.

## 19 · TestMeter — *prueba de concepto*

*Ruta: `/testmeter` — módulo `testmeter`, pública, fuera del menú*

Reconoce con IA los elementos de una foto de obra y estima sus
dimensiones reales.

- **Medidor por cámara** — reconoce puertas, huecos, enchufes… en una
  foto y estima su medida real.
- **Sin sesión ni organización** — página pública, limitada por IP, no
  aparece en Administración.

## 20 · Universo Plexo — *primera pieza*

*Ruta: `/plexo` — módulo `plexo`*

Punto de unión entre organizaciones de cuentas distintas: empresas que no
se conocían, encontrándose y conectando. Es la primera vez que algo cruza
a propósito la frontera de organización que el resto de la aplicación
mantiene siempre cerrada.

- **Perfil de visibilidad** — cada organización decide si se deja
  encontrar; apagado por defecto.
- **Buscar** — por nombre o CIF, solo entre las que se han hecho visibles.
- **Invitar y responder** — aceptar, rechazar o retirar una invitación;
  romper una conexión ya aceptada, desde cualquiera de los dos lados.
- **Sin duplicados** — como mucho una invitación viva por pareja de
  organizaciones; tras un rechazo o una ruptura se puede volver a
  intentar.

**Lo que falta, en orden:**

- **Intercambio de documentos** — enviar una factura o un presupuesto y
  que aparezca como un objeto real (no un PDF) en el Flexómetro del otro.
  Depende del vínculo, que ya existe.
- **Directorio** — buscar por especialidad y ubicación, no solo por
  nombre/CIF; aparecer en listas para que te inviten a colaborar en un
  proyecto.
- **Scoring** — necesita comportamiento real (intercambios, proyectos) de
  las dos piezas anteriores para significar algo.
- **Gamificación** — insignias y progreso para enseñar la interfaz.
  Independiente de todo lo demás; puede ir en paralelo.
- **Precios agregados (big data)** — a futuro. Necesita masa crítica de
  uso real y vivirá probablemente fuera del proceso de la API, como se
  habló para BIM/IFC.
