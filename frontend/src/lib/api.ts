import { organizacionActiva, tokenValido } from './auth'

export interface NavItem {
  label: string
  path: string
  icon: string
}

export interface Module {
  code: string
  name: string
  description: string
  icon: string
  depends_on: string[]
  always_active: boolean
  is_active: boolean
  nav: NavItem[]
  // Fase 17: qué tipo de documento numera este módulo (ver
  // `TipoDocumentoNumeracion`), si alguno — determina si el shell le pone un
  // botón de ajustes (rueda dentada).
  tipo_documento_numeracion: TipoDocumentoNumeracion | null
}

export interface Principal {
  username: string
  // null para el personal de la plataforma (rol superadmin sin
  // organización propia, Fase 13).
  organization_id: string | null
  organization_slug: string | null
  roles: string[]
  organizaciones: string[]
}

// --- Administración de cuentas y organizaciones (rol superadmin) ---
//
// Desde la Fase 14, Cuenta es el contrato de pago (puede agrupar varias
// organizaciones/CIFs); Organización sigue siendo el límite de aislamiento
// de datos de negocio, pero ya no lleva su propia tarifa ni facturación —
// eso vive en su Cuenta.

export interface CuentaAdmin {
  id: string
  nombre: string
  is_active: boolean
  tarifa_id: string | null
  // Fase 15: si está activo, terceros/banco de precios se ven (solo
  // lectura) entre las organizaciones de esta cuenta. Presupuestos, obras,
  // facturas... nunca se comparten, sin importar este valor.
  compartir_maestros: boolean
  created_at: string
}

export interface CuentaAdminDetalle extends CuentaAdmin {
  settings: Record<string, unknown>
  // Aviso (no bloqueo) para la pantalla de numeración: sus organizaciones
  // tienen CIF distinto, así que compartir secuencia entre ellas puede
  // incumplir la correlatividad exigida a cada una por separado.
  cifs_distintos: boolean
}

// --- Diccionario de referencia (Fase 18) ---
//
// Listas editables por cuenta (países, formas de pago...). `forma_pago`
// comparte claves con el enum `FormaPago` de más abajo, que sigue siendo
// quien de verdad restringe qué acepta la base de datos en un tercero o un
// cobro — el diccionario solo decide etiqueta, orden y activación.

export type TipoDiccionario =
  | 'pais'
  | 'forma_pago'
  | 'provincia'
  | 'unidad_medida'
  | 'forma_juridica'
  | 'tratamiento'
  | 'cargo'
  | 'iva'
  | 'recargo_equivalencia'
  | 'retencion'

export interface EntradaDiccionario {
  id: string
  tipo: TipoDiccionario
  clave: string
  etiqueta: string
  /** Solo en diccionarios de tipo/tasa (iva, recargo_equivalencia,
   *  retencion) — el porcentaje que representa la entrada. */
  valor: string | null
  activo: boolean
  orden: number
}

export interface TraduccionOverride {
  clave: string
  texto: string
}

/** Monedas y tipo de cambio (Fase 23) — a nivel de plataforma, solo de
 *  referencia: ningún presupuesto/factura se emite todavía en otra moneda
 *  que no sea EUR. */
export interface Moneda {
  id: string
  codigo: string
  nombre: string
  simbolo: string
  unidades_por_euro: string | null
  actualizado_en: string | null
}

// --- Campos libres (Fase 21-22) ---
//
// Extrafields al estilo Dolibarr: el admin de organización define qué campos
// existen para cada tipo de entidad (a nivel cuenta); los valores viven por
// registro concreto, protegidos por RLS de organización como cualquier dato
// de negocio.

export type EntidadCampoLibre =
  | 'tercero'
  | 'concepto'
  | 'obra'
  | 'presupuesto'
  | 'capitulo'
  | 'partida'
  | 'linea_medicion'
  | 'asignacion'
  | 'parte_trabajo'

export type TipoCampoLibre = 'texto' | 'numero' | 'fecha' | 'booleano' | 'select'

export interface CampoLibreDefinicion {
  id: string
  clave: string
  etiqueta: string
  tipo: TipoCampoLibre
  opciones: string[]
  requerido: boolean
  orden: number
  activo: boolean
}

export type TipoDocumentoNumeracion = 'presupuesto' | 'albaran' | 'factura'

export interface PatronNumeracion {
  tipo_documento: TipoDocumentoNumeracion
  patron: string
  secuencia_compartida: boolean
}

export interface NumeracionInfo {
  patrones: PatronNumeracion[]
  cifs_distintos: boolean
}

export interface OrganizacionAdmin {
  id: string
  cuenta_id: string
  slug: string
  name: string
  cif: string | null
  is_active: boolean
  created_at: string
}

export interface ModuloEstado {
  code: string
  name: string
  depends_on: string[]
  always_active: boolean
  is_active: boolean
}

export interface OrganizacionAdminDetalle extends OrganizacionAdmin {
  settings: Record<string, unknown>
  modulos: ModuloEstado[]
}

// --- Tarifas y descuentos ---

export interface TarifaModulo {
  module_code: string
  precio_mensual: string
}

export interface Tarifa {
  id: string
  nombre: string
  descripcion: string | null
  activa: boolean
  precio_1000_tokens_deepseek: string
  precio_1000_tokens_gemini: string
  // Créditos IA (Fase 38): unidad propia para el usuario final, ver
  // `api.creditosIA`.
  valor_credito_euros: string
  creditos_ia_incluidos_mes: number
  created_at: string
}

export interface TarifaDetalle extends Tarifa {
  modulos: TarifaModulo[]
}

export interface CreditosIA {
  consumidos: number
  incluidos: number
  sin_tarifa: boolean
}

export type TipoDescuento = 'porcentaje' | 'importe_fijo'

export type MotivoDescuento =
  | 'primer_mes_gratis'
  | 'fidelizacion'
  | 'retencion'
  | 'campana'
  | 'aumento_modulos'
  | 'otro'

export interface Descuento {
  id: string
  tarifa_id: string | null
  nombre: string
  motivo: MotivoDescuento
  tipo: TipoDescuento
  valor: string
  vigente_desde: string | null
  vigente_hasta: string | null
  activo: boolean
}

export interface AplicacionDescuento {
  id: string
  cuenta_id: string
  descuento: Descuento
  aplicado_en: string
  anulado_en: string | null
  vigente: boolean
}

export interface CosteEstimado {
  tarifa_nombre: string | null
  subtotal_modulos: string
  subtotal_ia: string
  subtotal: string
  descuentos_aplicados: string
  total: string
  tokens_deepseek_mes: number
  tokens_gemini_mes: number
}

export interface CobroSaas {
  id: string
  cuenta_id: string
  concepto: string
  importe: string
  fecha: string
  origen: string
  referencia_externa: string | null
  notas: string | null
}

export interface UsoIA {
  id: string
  usuario_subject: string
  usuario_nombre: string
  proveedor: string
  modelo: string
  tokens_entrada: number
  tokens_salida: number
  referencia: string | null
  created_at: string
}

// --- Ajustes globales ---

export interface ConfiguracionIA {
  deepseek_configurada: boolean
  deepseek_model: string
  deepseek_base_url: string
  gemini_configurada: boolean
  gemini_model: string
  gemini_base_url: string
}

export interface ConfiguracionSmtp {
  host: string | null
  puerto: number
  usuario: string | null
  remitente: string | null
  usa_tls: boolean
  tiene_password: boolean
}

export interface PruebaSmtp {
  enviado: boolean
  error: string | null
}

export interface ConfiguracionPasarela {
  proveedor: string
  vendor_id: string | null
  tiene_api_key: boolean
  activa: boolean
}

export interface UsuarioCreado {
  keycloak_user_id: string
  username: string
  email: string
  email_enviado: boolean
}

// --- Usuarios y grupos (Fase 12) ---

export interface UsuarioKeycloak {
  id: string
  username: string
  email: string | null
  firstName: string | null
  lastName: string | null
  enabled: boolean
  roles: string[]
}

export type Alcance = 'ninguno' | 'propios' | 'todos'

export interface ModuloDisponible {
  code: string
  name: string
}

export interface GrupoPermiso {
  module_code: string
  ver: Alcance
  editar: Alcance
}

export interface GrupoMiembro {
  id: string
  usuario_subject: string
  usuario_nombre: string
}

export interface Grupo {
  id: string
  organization_id: string
  nombre: string
  descripcion: string | null
  created_at: string
  permisos: GrupoPermiso[]
  miembros: GrupoMiembro[]
}

/** Mismo contrato para el panel de superadmin (cualquier organización) y el
 *  autoservicio del propio tenant: cambia a qué URL apuntan las funciones,
 *  no la forma de los datos ni la pantalla que las consume. */
export interface UsuariosGruposAPI {
  usuarios: {
    list: () => Promise<UsuarioKeycloak[]>
    create: (datos: {
      username: string
      email: string
      nombre: string
      apellidos: string
      es_admin?: boolean
    }) => Promise<UsuarioCreado>
    update: (
      id: string,
      datos: { email?: string; nombre?: string; apellidos?: string; habilitado?: boolean },
    ) => Promise<UsuarioKeycloak>
    remove: (id: string) => Promise<void>
    reenviar: (
      id: string,
      datos: { username: string; email: string; nombre: string },
    ) => Promise<UsuarioCreado>
  }
  grupos: {
    list: () => Promise<Grupo[]>
    create: (datos: { nombre: string; descripcion?: string | null }) => Promise<Grupo>
    update: (
      id: string,
      datos: { nombre?: string; descripcion?: string | null },
    ) => Promise<Grupo>
    remove: (id: string) => Promise<void>
    setPermisos: (id: string, permisos: GrupoPermiso[]) => Promise<Grupo>
    addMiembro: (
      id: string,
      datos: { usuario_subject: string; usuario_nombre: string },
    ) => Promise<Grupo>
    removeMiembro: (grupoId: string, miembroId: string) => Promise<void>
  }
  modulosDisponibles: () => Promise<ModuloDisponible[]>
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type TipoPersona = 'fisica' | 'juridica'
export type OrigenDato = 'manual' | 'fiebdc3' | 'ia' | 'importado'
export type TipoIVA = 'general' | 'reducido' | 'superreducido' | 'exento'
export type FormaPago =
  | 'transferencia'
  | 'domiciliado'
  | 'pagare'
  | 'confirming'
  | 'efectivo'
  | 'tarjeta'

export interface Contacto {
  id: string
  tercero_id: string | null
  tratamiento: string | null
  nombre: string
  apellidos: string | null
  cargo: string | null
  email: string | null
  telefono: string | null
  movil: string | null
  es_principal: boolean
  notas: string | null
  activo: boolean
}

export interface Tercero {
  id: string
  codigo: string
  nif: string | null
  razon_social: string
  nombre_comercial: string | null
  tipo_persona: TipoPersona
  forma_juridica: string | null
  es_cliente: boolean
  es_proveedor: boolean
  es_subcontratista: boolean
  email: string | null
  telefono: string | null
  web: string | null
  direccion: string | null
  codigo_postal: string | null
  ciudad: string | null
  provincia: string | null
  pais: string
  iban: string | null
  forma_pago: FormaPago | null
  dias_pago: number | null
  irpf_retencion: string | null
  inversion_sujeto_pasivo: boolean
  rea_numero: string | null
  rea_caducidad: string | null
  notas: string | null
  activo: boolean
  origen_dato: OrigenDato
}

export interface TerceroDetalle extends Tercero {
  contactos: Contacto[]
}

// --- Contactos asociados (Fase 28) ---
//
// Vínculo N a N entre un Contacto y cualquier objeto "grande" del negocio
// (presupuesto, obra, certificación, factura) — no requiere que el contacto
// pertenezca a un Tercero.

export type EntidadContacto = 'presupuesto' | 'obra' | 'certificacion' | 'factura'

export interface ContactoAsociado {
  id: string
  entidad: EntidadContacto
  entidad_id: string
  contacto_id: string
  rol: string | null
  created_at: string
  contacto_nombre: string
  contacto_apellidos: string | null
  contacto_cargo: string | null
  contacto_email: string | null
  contacto_telefono: string | null
}

// --- CRM / notas (Fase 29) ---
//
// --- Historial de cambios (Fase 38) ---
//
// Cada endpoint vive bajo su propio router (`/api/<recurso>/{id}/historial`),
// no uno genérico: así el permiso que se comprueba es siempre el mismo que
// ya protege la ficha (incluido "solo lo mío"), sin duplicar esa lógica aquí.

// 'evento': una acción del servidor que no es un diff de columnas de la
// propia entidad (la IA añadiendo un capítulo con partidas a un
// presupuesto, por ejemplo) — lleva `descripcion` en vez de `cambios`.
export type AccionAuditoria = 'creado' | 'modificado' | 'eliminado' | 'evento'

export interface CambioCampo {
  campo: string
  antes: unknown
  despues: unknown
}

export interface RegistroAuditoria {
  id: string
  accion: AccionAuditoria
  cambios: CambioCampo[] | null
  descripcion: string | null
  usuario_subject: string | null
  usuario_nombre: string | null
  created_at: string
}

// Cuaderno de bitácora del equipo sobre un objeto grande del negocio —
// mismo alcance de entidades que `EntidadContacto`, más 'tercero'.

export type EntidadNota = 'tercero' | 'presupuesto' | 'obra' | 'certificacion' | 'factura'

export interface Nota {
  id: string
  entidad: EntidadNota
  entidad_id: string
  contenido: string
  created_at: string
  creado_por_nombre: string | null
}

// --- Gestor documental (Fase 30) ---
//
// Ficheros subidos sobre un objeto grande del negocio, guardados en MinIO —
// mismo alcance de entidades que `EntidadNota`.

export type EntidadDocumento = 'tercero' | 'presupuesto' | 'obra' | 'certificacion' | 'factura'

export interface Documento {
  id: string
  entidad: EntidadDocumento
  entidad_id: string
  nombre_archivo: string
  content_type: string
  tamano_bytes: number
  created_at: string
  creado_por_nombre: string | null
}

export interface Familia {
  id: string
  codigo: string
  nombre: string
  parent_id: string | null
  orden: number
}

export interface PrecioSuministro {
  id: string
  concepto_id: string
  proveedor_id: string
  proveedor_razon_social: string | null
  precio: string
  precio_neto: string
  moneda: string
  descuento: string
  cantidad_minima: string | null
  plazo_entrega_dias: number | null
  referencia_proveedor: string | null
  vigente_desde: string
  vigente_hasta: string | null
  es_preferente: boolean
  origen_dato: OrigenDato
  notas: string | null
}

export type TipoConcepto = 'basico' | 'auxiliar' | 'unitario'
export type OrigenPrecio = 'manual' | 'producto' | 'descomposicion'
export type NaturalezaConcepto =
  | 'sin_clasificar'
  | 'mano_obra'
  | 'maquinaria'
  | 'material'
  | 'servicio'
  | 'residuo'
  | 'otro'

// "Banco de precios" (Fase 25): un producto/servicio del antiguo catálogo y
// una partida unitaria/precio descompuesto son la misma ficha.
export interface Concepto {
  id: string
  codigo: string
  tipo: TipoConcepto
  naturaleza: NaturalezaConcepto
  unidad: string
  resumen: string
  texto: string | null
  precio: string
  origen_precio: OrigenPrecio
  costes_indirectos: string | null
  fecha_precio: string | null
  ean: string | null
  familia_id: string | null
  precio_venta: string | null
  tipo_iva: TipoIVA
  activo: boolean
  origen_dato: OrigenDato
}

export interface Linea {
  id: string
  hijo_id: string
  hijo_codigo: string
  hijo_resumen: string
  hijo_unidad: string
  hijo_tipo: TipoConcepto
  hijo_precio: string
  rendimiento: string
  factor: string
  orden: number
  importe: string
}

export interface ConceptoDetalle extends Concepto {
  lineas: Linea[]
  coste_directo: string
  clase: string | null
  suministros: PrecioSuministro[]
}

export interface HistoricoPrecio {
  id: string
  precio: string
  origen_precio: OrigenPrecio
  fecha: string
}

export interface PartidaUso {
  id: string
  presupuesto_id: string
  presupuesto_nombre: string
  presupuesto_estado: string
  codigo: string
  resumen: string
  medicion: string
  precio: string
  importe: string
}

export interface UsoCompleto {
  en_descomposiciones: Uso[]
  en_partidas: PartidaUso[]
}

export interface Ventas {
  presupuestado_partidas: number
  presupuestado_importe: string
  facturado_lineas: number
  facturado_importe: string
}

export type EstadoPresupuesto =
  | 'borrador'
  | 'emitido'
  | 'aprobado'
  | 'rechazado'
  | 'cancelado'

export interface LineaMedicion {
  id: string
  partida_id: string
  comentario: string | null
  uds: string | null
  longitud: string | null
  anchura: string | null
  altura: string | null
  parcial: string
  orden: number
  /** Con fórmula (Fase 37), el parcial sale de la expresión y de estos valores. */
  formula_id: string | null
  formula_expresion: string | null
  formula_valores: Record<string, string>
}

export interface Partida {
  id: string
  capitulo_id: string
  concepto_id: string | null
  codigo: string
  resumen: string
  texto: string | null
  unidad: string
  precio: string
  medicion: string
  importe: string
  orden: number
  /** --- Venta (Fase 35) --- */
  precio_venta: string
  venta_bloqueada: boolean
  importe_venta: string
  /** Semáforo: `perdida` (va por debajo del coste), `bajo` (gana menos de lo
   *  previsto por el método) u `ok`. */
  estado_venta: 'perdida' | 'bajo' | 'ok'
  /** Solo lo llevan las partidas con descompuesto propio (Fase 34). */
  costes_indirectos: string | null
  /** Con desglose, la medición es la suma de sus parciales y no se teclea
   *  directamente en la rejilla (Fase 33). */
  tiene_desglose: boolean
  /** Se ha independizado del banco: su precio sale de su propio descompuesto
   *  (Fase 34). */
  descomposicion_propia: boolean
}

export interface PartidaDetalle extends Partida {
  lineas: LineaMedicion[]
  precio_cuadro: string | null
}

export interface NodoCapitulo {
  id: string
  codigo: string
  resumen: string
  texto: string | null
  orden: number
  importe: string
  importe_venta: string
  partidas: Partida[]
  hijos: NodoCapitulo[]
}

export interface Totales {
  metodo: MetodoCalculo
  porcentaje_metodo: string
  coste: string
  pem: string
  gastos_generales: string
  beneficio_industrial: string
  /** Diferencia entre el encadenado teórico y la venta real, por las partidas
   *  con la venta bloqueada a mano (Fase 35). */
  ajuste_manual: string
  incremento: string
  venta_sin_iva: string
  pec_sin_iva: string
  porcentaje_iva: string
  iva: string
  total: string
  margen: string
  margen_pct: string
}

export interface Version {
  id: string
  codigo: string
  nombre: string
  version: number
  estado: EstadoPresupuesto
  fecha: string | null
  created_at: string
}

/** Un cambio de celda de la rejilla del presupuesto (Fase 33). Solo se mandan
 *  los campos realmente editados; el resto no se toca en el servidor. */
export interface CambioLinea {
  id: string
  tipo: 'capitulo' | 'partida'
  codigo?: string
  resumen?: string
  texto?: string | null
  unidad?: string
  precio?: string
  medicion?: string
  precio_venta?: string
  venta_bloqueada?: boolean
}

/** Una línea del descompuesto de una partida (Fase 34). */
export interface LineaDescomposicion {
  id: string
  hijo_id: string | null
  codigo: string
  resumen: string
  unidad: string
  naturaleza: NaturalezaConcepto | null
  rendimiento: string
  factor: string
  precio: string
  importe: string
}

export interface DescomposicionPartida {
  /** `false` = todavía hereda el descompuesto del banco (solo lectura). */
  propia: boolean
  lineas: LineaDescomposicion[]
}

export type AlcancePrecio = 'partida' | 'presupuesto'

/** Portapapeles (Fase 1b): `copiar` clona, `mover` reengancha lo mismo al
 *  destino sin duplicar. */
export type AlcancePegado = 'copiar' | 'mover'
export interface ResultadoPegado {
  pegadas: number
}

export interface FormulaMedicion {
  id: string
  nombre: string
  expresion: string
  descripcion: string | null
  orden: number
  activa: boolean
  /** Deducidas de la expresión en el servidor. */
  variables: string[]
}

export type TipoReajuste = 'importe' | 'margen'

export interface LineaReajuste {
  partida_id: string
  codigo: string
  resumen: string
  bloqueada: boolean
  coste: string
  venta_antes: string
  venta_despues: string
  importe_antes: string
  importe_despues: string
}

export interface Reajuste {
  aplicado: boolean
  metodo: MetodoCalculo
  objetivo_venta: string
  coste: string
  venta_antes: string
  venta_despues: string
  /** Lo que se queda cerca del objetivo por el redondeo de precios unitarios. */
  diferencia: string
  margen_antes: string
  margen_despues: string
  /** El porcentaje único del método (el %GG+%BI combinado en el clásico) que
   *  deja la venta en el objetivo — es lo que de verdad cambia: un valor fijo
   *  y consistente, no un factor de escala ad hoc. */
  porcentaje_anterior: string
  porcentaje_nuevo: string
  partidas_afectadas: number
  partidas_bloqueadas: number
  partidas_bajo_coste: number
  lineas: LineaReajuste[]
}

export type MetodoCalculo = 'clasico' | 'incremento_sobre_coste' | 'beneficio_final'

export const ETIQUETA_METODO: Record<MetodoCalculo, string> = {
  clasico: 'Clásico (PEM + %GG + %BI)',
  incremento_sobre_coste: 'Coste + % de incremento sobre el coste',
  beneficio_final: 'Coste + % de beneficio final (sobre la venta)',
}

export interface RecursoAgregado {
  concepto_id: string
  codigo: string
  resumen: string
  unidad: string
  cantidad: string
  precio: string
  importe: string
}

export interface RecursosPresupuesto {
  materiales: RecursoAgregado[]
  mano_obra: RecursoAgregado[]
  horas_totales: string
}

export interface Cambio {
  codigo: string
  resumen: string
  unidad: string
  medicion_a: string | null
  medicion_b: string | null
  precio_a: string | null
  precio_b: string | null
  importe_a: string
  importe_b: string
  delta: string
}

export interface Comparacion {
  a: Version
  b: Version
  total_a: string
  total_b: string
  delta_total: string
  altas: Cambio[]
  bajas: Cambio[]
  cambios: Cambio[]
  sin_cambios: number
}

export interface Presupuesto {
  id: string
  codigo: string
  nombre: string
  descripcion: string | null
  cliente_id: string | null
  emplazamiento: string | null
  fecha: string | null
  validez_dias: number | null
  estado: EstadoPresupuesto
  raiz_id: string | null
  version: number
  es_plantilla: boolean
  tipo_obra: string | null
  gastos_generales: string
  beneficio_industrial: string
  tipo_iva: TipoIVA
  inversion_sujeto_pasivo: boolean
  metodo_calculo: MetodoCalculo
  porcentaje_metodo: string
  precios_bloqueados: boolean
  notas: string | null
  origen_dato: OrigenDato
  created_at: string
  updated_at: string
  creado_por_nombre: string | null
  responsable_subject: string | null
  responsable_nombre: string | null
}

export interface PresupuestoResumen extends Presupuesto {
  pem: string
  total: string
}

export interface PresupuestoDetalle extends Presupuesto {
  capitulos: NodoCapitulo[]
  totales: Totales
  partidas_desactualizadas: number
}

export type EstadoObra = 'planificada' | 'en_ejecucion' | 'paralizada' | 'finalizada' | 'cerrada'
export type EstadoAlbaran = 'borrador' | 'conformado' | 'facturado'

export interface Personal {
  id: string
  codigo: string
  nombre: string
  apellidos: string | null
  categoria: string | null
  coste_hora: string
  activo: boolean
  notas: string | null
}

export interface ParteTrabajo {
  id: string
  asignacion_id: string
  fecha: string
  horas: string
  capitulo_id: string | null
  coste: string
  notas: string | null
}

export interface Asignacion {
  id: string
  obra_id: string
  personal_id: string
  coste_hora: string
  fecha_desde: string
  fecha_hasta: string | null
  notas: string | null
}

export interface AsignacionDetalle extends Asignacion {
  personal_nombre: string
  personal_categoria: string | null
  partes: ParteTrabajo[]
  horas_totales: string
  coste_total: string
}

export interface Obra {
  id: string
  codigo: string
  nombre: string
  presupuesto_id: string
  jefe_obra_id: string | null
  estado: EstadoObra
  fecha_inicio: string | null
  fecha_fin_prevista: string | null
  fecha_fin_real: string | null
  notas: string | null
}

export interface ObraResumen extends Obra {
  presupuesto_codigo: string
  presupuesto_nombre: string
  pem: string
}

export interface ObraDetalle extends Obra {
  presupuesto_codigo: string
  presupuesto_nombre: string
  asignaciones: Asignacion[]
}

export interface AlbaranLinea {
  id: string
  albaran_id: string
  concepto_id: string | null
  capitulo_id: string | null
  descripcion: string
  unidad: string
  cantidad: string
  precio_unitario: string
  importe: string
  orden: number
}

export interface Albaran {
  id: string
  codigo: string
  obra_id: string
  proveedor_id: string
  numero_proveedor: string | null
  fecha: string
  estado: EstadoAlbaran
  notas: string | null
}

export interface AlbaranResumen extends Albaran {
  proveedor_razon_social: string
  total: string
}

export interface AlbaranDetalle extends Albaran {
  proveedor_razon_social: string
  lineas: AlbaranLinea[]
  total: string
}

export interface CosteCapitulo {
  capitulo_id: string | null
  codigo: string
  resumen: string
  presupuestado: string
  real_materiales: string
  real_mano_obra: string
  real_total: string
  desviacion: string
  desviacion_pct: string | null
}

export interface InformeCosteObra {
  obra_id: string
  obra_codigo: string
  obra_nombre: string
  capitulos: CosteCapitulo[]
  totales: CosteCapitulo
}

export type EstadoCertificacion = 'borrador' | 'emitida'
export type EstadoFactura = 'borrador' | 'emitida' | 'anulada'
export type SituacionCobro = 'pendiente' | 'parcial' | 'cobrada' | '-'

export interface CertificacionLinea {
  id: string
  partida_id: string
  codigo: string
  resumen: string
  unidad: string
  precio: string
  medicion_anterior: string
  medicion_actual: string
  medicion_periodo: string
  importe_periodo: string
  orden: number
}

export interface Certificacion {
  id: string
  codigo: string
  numero: number
  obra_id: string
  fecha: string
  estado: EstadoCertificacion
  retencion_garantia_pct: string
  notas: string | null
}

export interface CertificacionDetalle extends Certificacion {
  lineas: CertificacionLinea[]
  importe_ejecutado: string
  importe_retenido: string
  importe_liquido: string
  facturada: boolean
}

export interface Cobro {
  id: string
  factura_id: string
  fecha: string
  importe: string
  forma_pago: FormaPago | null
  notas: string | null
}

export interface Factura {
  id: string
  codigo: string
  serie: string
  numero: number | null
  obra_id: string
  certificacion_id: string | null
  cliente_id: string
  concepto: string
  fecha_emision: string | null
  fecha_vencimiento: string | null
  base_imponible: string
  tipo_iva: TipoIVA
  inversion_sujeto_pasivo: boolean
  cuota_iva: string
  total: string
  estado: EstadoFactura
  motivo_anulacion: string | null
  notificado_n8n_en: string | null
  notas: string | null
}

export interface FacturaResumen extends Factura {
  cliente_razon_social: string
  cobrado: string
  pendiente: string
  situacion_cobro: SituacionCobro
  vencida: boolean
}

export interface FacturaDetalle extends FacturaResumen {
  cobros: Cobro[]
}

// --- IA: sugerencia de patrones de presupuesto ---

export interface CapituloFrecuente {
  resumen: string
  veces: number
}

export interface PartidaFrecuente {
  concepto_id: string
  codigo: string
  resumen: string
  unidad: string
  veces: number
}

export interface Estadisticas {
  generico: boolean
  total_presupuestos: number
  capitulos: CapituloFrecuente[]
  partidas: PartidaFrecuente[]
}

export interface PartidaSugerida {
  concepto_id: string | null
  codigo: string | null
  resumen: string
  unidad: string
  precio: string | null
  es_nueva: boolean
}

export interface CapituloSugerido {
  resumen: string
  partidas: PartidaSugerida[]
}

export interface Sugerencia {
  id: string
  tipo_obra: string
  descripcion: string | null
  modelo: string
  plantilla_id: string | null
  created_at: string
}

export interface SugerenciaDetalle extends Sugerencia {
  capitulos: CapituloSugerido[]
}

export interface LineaSugerida {
  comentario: string | null
  uds: string | null
  longitud: string | null
  anchura: string | null
  altura: string | null
  parcial: string
}

export interface LecturaPlano {
  id: string
  partida_id: string | null
  fichero_nombre: string
  modelo: string
  observaciones: string | null
  aplicada_en: string | null
  created_at: string
}

export interface LecturaPlanoDetalle extends LecturaPlano {
  lineas: LineaSugerida[]
}

export interface Uso {
  id: string
  codigo: string
  resumen: string
  tipo: TipoConcepto
  precio: string
  rendimiento: string
}

/** Cabeceras comunes: el token del usuario y la organización activa.
 *
 *  La organización solo se envía cuando el usuario ha elegido una distinta de
 *  la primera; el backend rechaza cualquiera que no esté en su token, así que
 *  la cabecera no es una vía para colarse en otra. */
async function cabeceras(extra?: HeadersInit): Promise<Headers> {
  const h = new Headers(extra)
  const token = await tokenValido()
  if (token) h.set('Authorization', `Bearer ${token}`)
  const org = organizacionActiva()
  if (org) h.set('X-Organization-Slug', org)
  return h
}

/** Vite hace de proxy de /api hacia el contenedor de la API; en producción es
 *  Traefik quien sirve web y API bajo el mismo origen. En ambos casos, ruta
 *  relativa y sin CORS. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const h = await cabeceras(init?.headers)
  h.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...init, headers: h })
  if (!response.ok) {
    throw new Error(await mensajeDeError(response))
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

/** FastAPI devuelve `detail` como string en los HTTPException y como lista de
 *  errores en los 422 de validación; se aplanan a un texto legible. */
async function mensajeDeError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((e) => {
          const campo = Array.isArray(e.loc) ? e.loc.slice(1).join('.') : ''
          return campo ? `${campo}: ${e.msg}` : e.msg
        })
        .join(' · ')
    }
  } catch {
    /* respuesta sin cuerpo JSON */
  }
  return `${response.status} ${response.statusText}`
}

/** Descarga un fichero protegido.
 *
 *  Un `<a href>` no lleva la cabecera Authorization, así que con autenticación
 *  real hay que pedirlo por fetch y abrir el resultado como blob. `abrir` sirve
 *  para lo que el navegador sabe mostrar (PDF) y la descarga directa para lo
 *  que no (BC3).
 */
/** Qué llevar en un BC3/Excel (Fase 39) — coste y venta son excluyentes en
 *  BC3 (un solo precio por línea) pero libres en Excel; el modal es quien
 *  decide eso, aquí solo se serializan los que vengan marcados. */
export interface OpcionesExportacion {
  coste?: boolean
  venta?: boolean
  descompuestos?: boolean
  mediciones?: boolean
  descripcion?: boolean
}

function queryExportacion(opciones: OpcionesExportacion): string {
  const parametros = new URLSearchParams()
  for (const [clave, valor] of Object.entries(opciones)) {
    if (valor !== undefined) parametros.set(clave, String(valor))
  }
  return parametros.toString()
}

export interface PlantillaPresupuesto {
  id: string
  es_sistema: boolean
  nombre: string
  claves_detectadas: string[]
  activo: boolean
  created_at: string
}

export interface Empresa {
  id: string
  name: string
  cif: string | null
  direccion: string | null
  codigo_postal: string | null
  ciudad: string | null
  provincia: string | null
  telefono: string | null
  email: string | null
  web: string | null
  linkedin: string | null
  instagram: string | null
  facebook: string | null
  twitter: string | null
  politica_privacidad: string | null
  tiene_logo: boolean
}

export interface EmpresaResumen {
  id: string
  slug: string
  name: string
  cif: string | null
  is_active: boolean
  es_la_actual: boolean
}

export interface EmpresasCuenta {
  empresas: EmpresaResumen[]
  max_organizaciones: number
  puede_crear: boolean
}

/** Cualquier usuario autenticado puede verlo (es de marca, no un dato
 *  sensible) — no vive bajo /ajustes. Pídelo con `urlBlob()`, como cualquier
 *  imagen que necesite la cabecera Authorization. */
export const LOGO_ORGANIZACION_URL = '/api/organizacion/logo'

export async function descargar(
  path: string,
  nombre: string,
  opciones: { abrir?: boolean } = {},
): Promise<void> {
  const response = await fetch(path, { headers: await cabeceras() })
  if (!response.ok) throw new Error(await mensajeDeError(response))

  const url = URL.createObjectURL(await response.blob())
  if (opciones.abrir) {
    window.open(url, '_blank', 'noopener')
  } else {
    const enlace = document.createElement('a')
    enlace.href = url
    enlace.download = nombre
    enlace.click()
  }
  // Se libera con margen: revocarla de inmediato cancelaría la descarga o
  // dejaría la pestaña recién abierta sin contenido.
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** Como `descargar`, pero para mostrar el fichero incrustado (p. ej. una
 *  imagen dentro de una descripción con formato) en vez de guardarlo o
 *  abrirlo aparte — el `<img src>` no puede llevar la cabecera Authorization,
 *  así que hay que pedirlo por fetch y quedarse con la URL del blob mientras
 *  se muestre. Quien la pida es quien debe revocarla con `URL.revokeObjectURL`
 *  cuando deje de hacer falta.
 */
export async function urlBlob(path: string): Promise<string> {
  const response = await fetch(path, { headers: await cabeceras() })
  if (!response.ok) throw new Error(await mensajeDeError(response))
  return URL.createObjectURL(await response.blob())
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [clave, valor] of Object.entries(params)) {
    if (valor !== undefined && valor !== null && valor !== '') {
      search.set(clave, String(valor))
    }
  }
  const texto = search.toString()
  return texto ? `?${texto}` : ''
}

/** Igual que `request`, pero para un endpoint que devuelve un fichero (PDF)
 *  en vez de JSON — usado por la exportación de listados (`DataTable`). */
async function pedirBlob(path: string, body: unknown): Promise<Blob> {
  const h = await cabeceras()
  h.set('Content-Type', 'application/json')
  const response = await fetch(path, { method: 'POST', body: JSON.stringify(body), headers: h })
  if (!response.ok) throw new Error(await mensajeDeError(response))
  return response.blob()
}

/** Subida de fichero: va como multipart, así que no lleva Content-Type propio
 *  —el navegador tiene que añadir el boundary él mismo. */
async function subir<T>(path: string, formulario: FormData): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    body: formulario,
    headers: await cabeceras(),
  })
  if (!response.ok) throw new Error(await mensajeDeError(response))
  return response.json() as Promise<T>
}

/** Lo que puede proponer la IA en "Ayuda con IA" o en la conversación sobre
 *  un documento arrastrado — nunca lo ejecuta ella, solo deja la propuesta
 *  lista para que el usuario la confirme (ver `AyudaIAModal`/`DocumentoIAModal`). */
export interface ComponentePropuesto {
  concepto_id: string | null
  codigo: string | null
  resumen: string
  unidad: string
  rendimiento: string
  // Personalizado: no existe en el banco de precios, se da de alta al
  // confirmar con este precio/naturaleza (ver AyudaIAModal.confirmarCrear).
  personalizado: boolean
  precio: string | null
  naturaleza: string | null
}

export interface PartidaConComponentes {
  partida_id: string | null
  resumen: string | null
  unidad: string | null
  componentes: ComponentePropuesto[]
}

export interface CapituloPropuesto {
  resumen: string
  partidas: PartidaConComponentes[]
}

export interface PropuestaIA {
  tipo: 'copiar_partida' | 'crear_partida' | 'importar_capitulo' | 'crear_capitulos'
  descripcion: string
  // copiar_partida:
  partida_id: string | null
  // crear_partida:
  resumen: string | null
  unidad: string | null
  componentes: ComponentePropuesto[]
  // importar_capitulo (chat de documentos): partidas alzadas, con el precio
  // que trae el documento, no del banco de precios propio.
  capitulo_resumen: string | null
  partidas_propuestas: { resumen: string; unidad: string; precio: string; medicion: string }[]
  // crear_capitulos (Fase 42/42c, "Ayuda con IA"): uno o varios capítulos
  // de una vez (por ejemplo, todas las fases de obra) — cada partida de
  // cada capítulo es una ya existente que se mueve aquí (`partida_id`) o
  // una nueva con su descompuesto real contra el banco de precios.
  capitulos_propuestos: CapituloPropuesto[]
}

export interface AnalisisBC3 {
  version: string
  fecha: string
  programa: string
  cabecera: string
  codificacion: string
  es_presupuesto: boolean
  total_conceptos: number
  por_tipo: Record<string, number>
  lineas_descomposicion: number
  mediciones: number
  incidencias: string[]
}

export interface ImportacionBC3 {
  conceptos_creados: number
  conceptos_omitidos: number
  conceptos_actualizados: number
  lineas_descomposicion: number
  presupuesto_id: string | null
  capitulos: number
  partidas: number
  lineas_medicion: number
  discrepancias: number
  discrepancia_maxima: string
  ejemplos_discrepancia: { codigo: string; calculado: string; en_fichero: string }[]
  ciclos: string[]
  incidencias: string[]
}

const post = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) })
const patch = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
// Genérico porque algún DELETE devuelve el estado ya recalculado en vez de un
// 204 (ver `quitarComponente`); `request` ya distingue el 204 sin cuerpo.
const del = <T = void,>(path: string) => request<T>(path, { method: 'DELETE' })

export const api = {
  me: () => request<Principal>('/api/me'),
  modules: () => request<Module[]>('/api/modules'),
  setModuleActive: (code: string, active: boolean) =>
    post<string[]>(`/api/modules/${code}/${active ? 'activate' : 'deactivate'}`, {}),
  /** Créditos IA (Fase 38): consumo del mes en curso de la cuenta del
   *  usuario, en la unidad propia que sustituye a hablar de tokens de
   *  DeepSeek/Gemini por separado — ver `CreditosIA`. */
  creditosIA: {
    get: () => request<CreditosIA>('/api/creditos-ia'),
  },
  exportarPdf: (datos: { titulo: string; columnas: string[]; filas: string[][] }) =>
    pedirBlob('/api/exportar/pdf', datos),

  /** Lectura de diccionario para formularios de negocio (país de un
   *  tercero, forma de pago...) — cualquier usuario autenticado, solo
   *  entradas activas. Para editar, ver `ajustes.diccionario` más abajo. */
  diccionario: {
    list: (tipo: TipoDiccionario) => request<EntradaDiccionario[]>(`/api/diccionario/${tipo}`),
  },

  /** Overrides de traducción de la cuenta (Fase 19) — se funden sobre el
   *  bundle base al arrancar la sesión, ver `i18n/index.ts`. */
  traducciones: {
    list: () => request<Record<string, string>>('/api/traducciones'),
  },

  /** Monedas y tipo de cambio (Fase 23) — de plataforma, no de cuenta; se
   *  refresca sola si lleva más de 24h caducada. Para forzar un refresco,
   *  ver `ajustes.monedas.actualizar`. */
  monedas: {
    list: () => request<Moneda[]>('/api/monedas'),
  },

  /** Campos libres (Fase 21-22) — lectura de qué campos existen (para pintar
   *  el formulario) y de/hacia los valores de un registro concreto,
   *  protegido por RLS de organización. Para definir campos nuevos, ver
   *  `ajustes.camposLibres` más abajo. */
  camposLibres: {
    definiciones: (entidad: EntidadCampoLibre) =>
      request<CampoLibreDefinicion[]>(`/api/campos-libres/definiciones/${entidad}`),
    valores: (entidad: EntidadCampoLibre, entidadId: string) =>
      request<Record<string, string | null>>(`/api/campos-libres/${entidad}/${entidadId}`),
    establecerValores: (entidad: EntidadCampoLibre, entidadId: string, valores: Record<string, string | null>) =>
      request<Record<string, string | null>>(`/api/campos-libres/${entidad}/${entidadId}`, {
        method: 'PUT',
        body: JSON.stringify({ valores }),
      }),
  },

  /** Fase 17: autoservicio de ajustes de módulo — el admin de organización
   *  edita los de su propia cuenta, resuelta en el servidor a partir de su
   *  organización activa (nunca un parámetro que pueda apuntar a otra). */
  ajustes: {
    numeracion: () => request<NumeracionInfo>('/api/ajustes/numeracion'),
    actualizarNumeracion: (
      tipoDocumento: TipoDocumentoNumeracion,
      datos: { patron: string; secuencia_compartida: boolean },
    ) =>
      request<PatronNumeracion>(`/api/ajustes/numeracion/${tipoDocumento}`, {
        method: 'PUT',
        body: JSON.stringify(datos),
      }),
    /** Fase 40/41: hasta 2 empresas (CIFs) por cuenta, cada una con sus
     *  datos básicos, logo y política de privacidad — cualquiera de las de
     *  la propia cuenta es editable aquí, no solo la activa en la sesión. */
    empresas: {
      list: () => request<EmpresasCuenta>('/api/ajustes/empresas'),
      crear: (datos: { name: string; cif?: string | null }) =>
        post<EmpresaResumen>('/api/ajustes/empresas', datos),
      get: (id: string) => request<Empresa>(`/api/ajustes/empresas/${id}`),
      actualizar: (id: string, datos: Partial<Omit<Empresa, 'id' | 'tiene_logo'>>) =>
        patch<Empresa>(`/api/ajustes/empresas/${id}`, datos),
      logoUrl: (id: string) => `/api/ajustes/empresas/${id}/logo`,
      subirLogo: (id: string, archivo: File) => {
        const f = new FormData()
        f.append('archivo', archivo)
        return subir<Empresa>(`/api/ajustes/empresas/${id}/logo`, f)
      },
      eliminarLogo: (id: string) => request<Empresa>(`/api/ajustes/empresas/${id}/logo`, { method: 'DELETE' }),
    },
    /** Fase 39: plantillas Word para exportar presupuestos — de sistema
     *  (no editables) más las propias de la cuenta. */
    plantillasPresupuesto: {
      list: () => request<PlantillaPresupuesto[]>('/api/ajustes/plantillas-presupuesto'),
      subir: (nombre: string, archivo: File) => {
        const f = new FormData()
        f.append('nombre', nombre)
        f.append('archivo', archivo)
        return subir<PlantillaPresupuesto>('/api/ajustes/plantillas-presupuesto', f)
      },
      eliminar: (id: string) => del(`/api/ajustes/plantillas-presupuesto/${id}`),
      descargarPatronUrl: (id: string) => `/api/ajustes/plantillas-presupuesto/${id}/descargar`,
    },
    /** Fase 18: mismo patrón, autoservicio de cuenta — CRUD completo (a
     *  diferencia de `diccionario.list`, que es de solo lectura para
     *  cualquier usuario). */
    diccionario: {
      list: (tipo: TipoDiccionario) =>
        request<EntradaDiccionario[]>(`/api/ajustes/diccionario/${tipo}`),
      create: (
        tipo: TipoDiccionario,
        datos: { clave: string; etiqueta: string; valor?: string | null; orden?: number },
      ) => post<EntradaDiccionario>(`/api/ajustes/diccionario/${tipo}`, datos),
      update: (
        tipo: TipoDiccionario,
        id: string,
        datos: { etiqueta?: string; valor?: string | null; activo?: boolean; orden?: number },
      ) => patch<EntradaDiccionario>(`/api/ajustes/diccionario/${tipo}/${id}`, datos),
      eliminar: (tipo: TipoDiccionario, id: string) => del(`/api/ajustes/diccionario/${tipo}/${id}`),
    },
    /** Fase 19: autoservicio de overrides de traducción, mismo patrón. */
    traduccion: {
      list: () => request<TraduccionOverride[]>('/api/ajustes/traduccion'),
      establecer: (clave: string, texto: string) =>
        request<TraduccionOverride>(`/api/ajustes/traduccion/${encodeURIComponent(clave)}`, {
          method: 'PUT',
          body: JSON.stringify({ texto }),
        }),
      eliminar: (clave: string) => del(`/api/ajustes/traduccion/${encodeURIComponent(clave)}`),
    },
    /** Fase 21: autoservicio de definición de campos libres, mismo patrón. */
    camposLibres: {
      list: (entidad: EntidadCampoLibre) =>
        request<CampoLibreDefinicion[]>(`/api/ajustes/campos-libres/${entidad}`),
      create: (
        entidad: EntidadCampoLibre,
        datos: {
          clave: string
          etiqueta: string
          tipo: TipoCampoLibre
          opciones?: string[]
          requerido?: boolean
          orden?: number
        },
      ) => post<CampoLibreDefinicion>(`/api/ajustes/campos-libres/${entidad}`, datos),
      update: (
        entidad: EntidadCampoLibre,
        id: string,
        datos: {
          etiqueta?: string
          tipo?: TipoCampoLibre
          opciones?: string[]
          requerido?: boolean
          orden?: number
          activo?: boolean
        },
      ) => patch<CampoLibreDefinicion>(`/api/ajustes/campos-libres/${entidad}/${id}`, datos),
      eliminar: (entidad: EntidadCampoLibre, id: string) => del(`/api/ajustes/campos-libres/${entidad}/${id}`),
    },
    /** Fase 23: forzar un refresco inmediato del tipo de cambio (dato de
     *  plataforma, no de esta cuenta — cualquier admin de organización
     *  puede dispararlo). */
    monedas: {
      actualizar: () => post<Moneda[]>('/api/ajustes/monedas/actualizar', {}),
    },
  },

  admin: {
    /** Desde la Fase 14, toda organización nace dentro de una cuenta — no
     *  hay alta ni listado plano aquí, ver `cuentas` más abajo. */
    organizaciones: {
      get: (id: string) => request<OrganizacionAdminDetalle>(`/api/admin/organizaciones/${id}`),
      update: (
        id: string,
        datos: { name?: string; cif?: string | null; is_active?: boolean },
      ) => patch<OrganizacionAdmin>(`/api/admin/organizaciones/${id}`, datos),
      setModuleActive: (id: string, code: string, active: boolean) =>
        post<string[]>(
          `/api/admin/organizaciones/${id}/modulos/${code}/${active ? 'activate' : 'deactivate'}`,
          {},
        ),
      smtp: {
        get: (id: string) => request<ConfiguracionSmtp>(`/api/admin/organizaciones/${id}/smtp`),
        update: (
          id: string,
          datos: {
            host?: string | null
            puerto?: number
            usuario?: string | null
            password?: string | null
            remitente?: string | null
            usa_tls?: boolean
          },
        ) => patch<ConfiguracionSmtp>(`/api/admin/organizaciones/${id}/smtp`, datos),
        probar: (id: string, destinatario: string) =>
          post<PruebaSmtp>(`/api/admin/organizaciones/${id}/smtp/prueba`, { destinatario }),
      },
      usuarios: {
        list: (id: string) =>
          request<UsuarioKeycloak[]>(`/api/admin/organizaciones/${id}/usuarios`),
        create: (
          id: string,
          datos: {
            username: string
            email: string
            nombre: string
            apellidos: string
            es_admin?: boolean
          },
        ) => post<UsuarioCreado>(`/api/admin/organizaciones/${id}/usuarios`, datos),
        update: (
          id: string,
          keycloakUserId: string,
          datos: { email?: string; nombre?: string; apellidos?: string; habilitado?: boolean },
        ) =>
          patch<UsuarioKeycloak>(
            `/api/admin/organizaciones/${id}/usuarios/${keycloakUserId}`,
            datos,
          ),
        remove: (id: string, keycloakUserId: string) =>
          del(`/api/admin/organizaciones/${id}/usuarios/${keycloakUserId}`),
        reenviar: (
          id: string,
          keycloakUserId: string,
          datos: { username: string; email: string; nombre: string },
        ) =>
          post<UsuarioCreado>(
            `/api/admin/organizaciones/${id}/usuarios/${keycloakUserId}/reenviar`,
            datos,
          ),
      },
      grupos: {
        modulosDisponibles: (id: string) =>
          request<ModuloDisponible[]>(`/api/admin/organizaciones/${id}/modulos-disponibles`),
        list: (id: string) => request<Grupo[]>(`/api/admin/organizaciones/${id}/grupos`),
        create: (id: string, datos: { nombre: string; descripcion?: string | null }) =>
          post<Grupo>(`/api/admin/organizaciones/${id}/grupos`, datos),
        update: (
          id: string,
          grupoId: string,
          datos: { nombre?: string; descripcion?: string | null },
        ) => patch<Grupo>(`/api/admin/organizaciones/${id}/grupos/${grupoId}`, datos),
        remove: (id: string, grupoId: string) =>
          del(`/api/admin/organizaciones/${id}/grupos/${grupoId}`),
        setPermisos: (id: string, grupoId: string, permisos: GrupoPermiso[]) =>
          request<Grupo>(`/api/admin/organizaciones/${id}/grupos/${grupoId}/permisos`, {
            method: 'PUT',
            body: JSON.stringify({ permisos }),
          }),
        addMiembro: (
          id: string,
          grupoId: string,
          datos: { usuario_subject: string; usuario_nombre: string },
        ) =>
          post<Grupo>(`/api/admin/organizaciones/${id}/grupos/${grupoId}/miembros`, datos),
        removeMiembro: (id: string, grupoId: string, miembroId: string) =>
          del(`/api/admin/organizaciones/${id}/grupos/${grupoId}/miembros/${miembroId}`),
      },
      /** Adapta los métodos de arriba (organizationId por parámetro) al
       *  contrato común `UsuariosGruposAPI`, que la pantalla comparte con el
       *  autoservicio del tenant. */
      usuariosYGrupos: (id: string): UsuariosGruposAPI => ({
        usuarios: {
          list: () => api.admin.organizaciones.usuarios.list(id),
          create: (datos) => api.admin.organizaciones.usuarios.create(id, datos),
          update: (userId, datos) => api.admin.organizaciones.usuarios.update(id, userId, datos),
          remove: (userId) => api.admin.organizaciones.usuarios.remove(id, userId),
          reenviar: (userId, datos) =>
            api.admin.organizaciones.usuarios.reenviar(id, userId, datos),
        },
        grupos: {
          list: () => api.admin.organizaciones.grupos.list(id),
          create: (datos) => api.admin.organizaciones.grupos.create(id, datos),
          update: (grupoId, datos) => api.admin.organizaciones.grupos.update(id, grupoId, datos),
          remove: (grupoId) => api.admin.organizaciones.grupos.remove(id, grupoId),
          setPermisos: (grupoId, permisos) =>
            api.admin.organizaciones.grupos.setPermisos(id, grupoId, permisos),
          addMiembro: (grupoId, datos) =>
            api.admin.organizaciones.grupos.addMiembro(id, grupoId, datos),
          removeMiembro: (grupoId, miembroId) =>
            api.admin.organizaciones.grupos.removeMiembro(id, grupoId, miembroId),
        },
        modulosDisponibles: () => api.admin.organizaciones.grupos.modulosDisponibles(id),
      }),
    },

    /** El contrato de pago (Fase 14): agrupa una o varias organizaciones.
     *  Tarifa asignada, cobros, uso de IA, descuentos y coste estimado
     *  viven aquí, consolidados entre todas sus organizaciones — ver
     *  `organizaciones` arriba para lo que sigue siendo por organización
     *  (módulos activos, SMTP propio, usuarios y grupos). */
    cuentas: {
      list: () => request<CuentaAdmin[]>('/api/admin/cuentas'),
      get: (id: string) => request<CuentaAdminDetalle>(`/api/admin/cuentas/${id}`),
      create: (datos: { nombre: string }) => post<CuentaAdminDetalle>('/api/admin/cuentas', datos),
      update: (
        id: string,
        datos: {
          nombre?: string
          is_active?: boolean
          tarifa_id?: string | null
          compartir_maestros?: boolean
        },
      ) => patch<CuentaAdminDetalle>(`/api/admin/cuentas/${id}`, datos),
      organizaciones: {
        list: (id: string) => request<OrganizacionAdmin[]>(`/api/admin/cuentas/${id}/organizaciones`),
        create: (id: string, datos: { name: string; cif?: string | null }) =>
          post<OrganizacionAdmin>(`/api/admin/cuentas/${id}/organizaciones`, datos),
      },
      costeEstimado: (id: string) =>
        request<CosteEstimado>(`/api/admin/cuentas/${id}/coste-estimado`),
      cobros: {
        list: (id: string) => request<CobroSaas[]>(`/api/admin/cuentas/${id}/cobros`),
        create: (
          id: string,
          datos: { concepto: string; importe: string; fecha: string; notas?: string | null },
        ) => post<CobroSaas>(`/api/admin/cuentas/${id}/cobros`, datos),
      },
      usoIA: (id: string, params: { limit?: number; offset?: number } = {}) =>
        request<UsoIA[]>(`/api/admin/cuentas/${id}/uso-ia${query(params)}`),
      descuentos: {
        list: (id: string) =>
          request<AplicacionDescuento[]>(`/api/admin/cuentas/${id}/descuentos`),
        aplicar: (id: string, descuentoIds: string[]) =>
          post<AplicacionDescuento[]>(`/api/admin/cuentas/${id}/descuentos`, {
            descuento_ids: descuentoIds,
          }),
        anular: (id: string, aplicacionId: string) =>
          post<AplicacionDescuento>(`/api/admin/cuentas/${id}/descuentos/${aplicacionId}/anular`, {}),
      },
      /** Fase 16: patrón del `codigo` interno de Presupuesto/Albarán/Factura
       *  — nunca la numeración fiscal (serie/número) de las facturas. */
      patronesNumeracion: {
        list: (id: string) =>
          request<PatronNumeracion[]>(`/api/admin/cuentas/${id}/patrones-numeracion`),
        update: (
          id: string,
          tipoDocumento: TipoDocumentoNumeracion,
          datos: { patron: string; secuencia_compartida: boolean },
        ) =>
          request<PatronNumeracion>(`/api/admin/cuentas/${id}/patrones-numeracion/${tipoDocumento}`, {
            method: 'PUT',
            body: JSON.stringify(datos),
          }),
      },
    },

    tarifas: {
      list: () => request<Tarifa[]>('/api/admin/tarifas'),
      get: (id: string) => request<TarifaDetalle>(`/api/admin/tarifas/${id}`),
      create: (datos: {
        nombre: string
        descripcion?: string | null
        precio_1000_tokens_deepseek?: string
        precio_1000_tokens_gemini?: string
        valor_credito_euros?: string
        creditos_ia_incluidos_mes?: number
        modulos: TarifaModulo[]
      }) => post<TarifaDetalle>('/api/admin/tarifas', datos),
      update: (
        id: string,
        datos: {
          nombre?: string
          descripcion?: string | null
          activa?: boolean
          precio_1000_tokens_deepseek?: string
          precio_1000_tokens_gemini?: string
          valor_credito_euros?: string
          creditos_ia_incluidos_mes?: number
          modulos?: TarifaModulo[]
        },
      ) => patch<TarifaDetalle>(`/api/admin/tarifas/${id}`, datos),
    },

    /** Superadmins de la plataforma: sin organización propia (Fase 13), por
     *  eso vive fuera de `organizaciones` y no recibe un `id` de tenant. */
    personalPlataforma: {
      list: () => request<UsuarioKeycloak[]>('/api/admin/personal-plataforma'),
      create: (datos: { username: string; email: string; nombre: string; apellidos: string }) =>
        post<UsuarioCreado>('/api/admin/personal-plataforma', datos),
      update: (
        keycloakUserId: string,
        datos: { email?: string; nombre?: string; apellidos?: string; habilitado?: boolean },
      ) => patch<UsuarioKeycloak>(`/api/admin/personal-plataforma/${keycloakUserId}`, datos),
      remove: (keycloakUserId: string) => del(`/api/admin/personal-plataforma/${keycloakUserId}`),
      reenviar: (
        keycloakUserId: string,
        datos: { username: string; email: string; nombre: string },
      ) => post<UsuarioCreado>(`/api/admin/personal-plataforma/${keycloakUserId}/reenviar`, datos),
    },

    descuentos: {
      list: (params: { tarifa_id?: string } = {}) =>
        request<Descuento[]>(`/api/admin/descuentos${query(params)}`),
      create: (datos: {
        tarifa_id?: string | null
        nombre: string
        motivo?: MotivoDescuento
        tipo: TipoDescuento
        valor: string
        vigente_desde?: string | null
        vigente_hasta?: string | null
      }) => post<Descuento>('/api/admin/descuentos', datos),
      update: (
        id: string,
        datos: {
          nombre?: string
          motivo?: MotivoDescuento
          valor?: string
          vigente_desde?: string | null
          vigente_hasta?: string | null
          activo?: boolean
        },
      ) => patch<Descuento>(`/api/admin/descuentos/${id}`, datos),
      remove: (id: string) => del(`/api/admin/descuentos/${id}`),
    },

    ajustesIA: {
      get: () => request<ConfiguracionIA>('/api/admin/ajustes-ia'),
      update: (datos: {
        deepseek_api_key?: string | null
        deepseek_model?: string
        deepseek_base_url?: string
        gemini_api_key?: string | null
        gemini_model?: string
        gemini_base_url?: string
      }) => patch<ConfiguracionIA>('/api/admin/ajustes-ia', datos),
    },

    ajustesSmtp: {
      get: () => request<ConfiguracionSmtp>('/api/admin/ajustes-smtp'),
      update: (datos: {
        host?: string | null
        puerto?: number
        usuario?: string | null
        password?: string | null
        remitente?: string | null
        usa_tls?: boolean
      }) => patch<ConfiguracionSmtp>('/api/admin/ajustes-smtp', datos),
      probar: (destinatario: string) =>
        post<PruebaSmtp>('/api/admin/ajustes-smtp/prueba', { destinatario }),
    },

    pasarelaPago: {
      get: () => request<ConfiguracionPasarela>('/api/admin/pasarela-pago'),
      update: (datos: {
        proveedor?: string
        api_key?: string | null
        vendor_id?: string | null
        activa?: boolean
      }) => patch<ConfiguracionPasarela>('/api/admin/pasarela-pago', datos),
    },
  },

  /** Autoservicio de usuarios y grupos de la propia organización: mismo
   *  contrato que `admin.organizaciones.usuariosYGrupos(id)`, gated en el
   *  backend por el rol `admin` en vez de `superadmin`. */
  usuariosYGrupos: {
    usuarios: {
      list: () => request<UsuarioKeycloak[]>('/api/usuarios'),
      create: (datos: {
        username: string
        email: string
        nombre: string
        apellidos: string
        es_admin?: boolean
      }) => post<UsuarioCreado>('/api/usuarios', datos),
      update: (
        id: string,
        datos: { email?: string; nombre?: string; apellidos?: string; habilitado?: boolean },
      ) => patch<UsuarioKeycloak>(`/api/usuarios/${id}`, datos),
      remove: (id: string) => del(`/api/usuarios/${id}`),
      reenviar: (id: string, datos: { username: string; email: string; nombre: string }) =>
        post<UsuarioCreado>(`/api/usuarios/${id}/reenviar`, datos),
    },
    grupos: {
      list: () => request<Grupo[]>('/api/grupos'),
      create: (datos: { nombre: string; descripcion?: string | null }) =>
        post<Grupo>('/api/grupos', datos),
      update: (id: string, datos: { nombre?: string; descripcion?: string | null }) =>
        patch<Grupo>(`/api/grupos/${id}`, datos),
      remove: (id: string) => del(`/api/grupos/${id}`),
      setPermisos: (id: string, permisos: GrupoPermiso[]) =>
        request<Grupo>(`/api/grupos/${id}/permisos`, {
          method: 'PUT',
          body: JSON.stringify({ permisos }),
        }),
      addMiembro: (id: string, datos: { usuario_subject: string; usuario_nombre: string }) =>
        post<Grupo>(`/api/grupos/${id}/miembros`, datos),
      removeMiembro: (grupoId: string, miembroId: string) =>
        del(`/api/grupos/${grupoId}/miembros/${miembroId}`),
    },
    modulosDisponibles: () => request<ModuloDisponible[]>('/api/modulos-disponibles'),
  } satisfies UsuariosGruposAPI,

  terceros: {
    list: (params: { q?: string; rol?: string; activo?: boolean; limit?: number; offset?: number }) =>
      request<Page<Tercero>>(`/api/terceros${query(params)}`),
    get: (id: string) => request<TerceroDetalle>(`/api/terceros/${id}`),
    create: (datos: Partial<Tercero>) => post<TerceroDetalle>('/api/terceros', datos),
    update: (id: string, datos: Partial<Tercero>) =>
      patch<Tercero>(`/api/terceros/${id}`, datos),
    remove: (id: string) => del(`/api/terceros/${id}`),
    historial: (id: string) => request<RegistroAuditoria[]>(`/api/terceros/${id}/historial`),
  },

  contactos: {
    list: (params: { tercero_id?: string; q?: string; limit?: number; offset?: number }) =>
      request<Page<Contacto>>(`/api/contactos${query(params)}`),
    create: (datos: Partial<Contacto>) => post<Contacto>('/api/contactos', datos),
    update: (id: string, datos: Partial<Contacto>) =>
      patch<Contacto>(`/api/contactos/${id}`, datos),
    remove: (id: string) => del(`/api/contactos/${id}`),
  },

  contactosAsociados: {
    list: (entidad: EntidadContacto, entidadId: string) =>
      request<ContactoAsociado[]>(`/api/contactos-asociados${query({ entidad, entidad_id: entidadId })}`),
    create: (entidad: EntidadContacto, entidadId: string, datos: { contacto_id: string; rol?: string | null }) =>
      post<ContactoAsociado>(`/api/contactos-asociados${query({ entidad, entidad_id: entidadId })}`, datos),
    remove: (id: string) => del(`/api/contactos-asociados/${id}`),
  },

  notas: {
    list: (entidad: EntidadNota, entidadId: string) =>
      request<Nota[]>(`/api/notas${query({ entidad, entidad_id: entidadId })}`),
    create: (entidad: EntidadNota, entidadId: string, contenido: string) =>
      post<Nota>(`/api/notas${query({ entidad, entidad_id: entidadId })}`, { contenido }),
    remove: (id: string) => del(`/api/notas/${id}`),
  },

  documentos: {
    list: (entidad: EntidadDocumento, entidadId: string) =>
      request<Documento[]>(`/api/documentos${query({ entidad, entidad_id: entidadId })}`),
    upload: (entidad: EntidadDocumento, entidadId: string, fichero: File) => {
      const formulario = new FormData()
      formulario.append('entidad', entidad)
      formulario.append('entidad_id', entidadId)
      formulario.append('fichero', fichero)
      return subir<Documento>('/api/documentos', formulario)
    },
    descargarUrl: (id: string) => `/api/documentos/${id}/descargar`,
    remove: (id: string) => del(`/api/documentos/${id}`),
  },

  familias: {
    list: () => request<Familia[]>('/api/familias'),
    create: (datos: Partial<Familia>) => post<Familia>('/api/familias', datos),
    update: (id: string, datos: Partial<Familia>) =>
      patch<Familia>(`/api/familias/${id}`, datos),
    remove: (id: string) => del(`/api/familias/${id}`),
  },

  suministros: {
    update: (id: string, datos: Partial<PrecioSuministro>) =>
      patch<PrecioSuministro>(`/api/suministros/${id}`, datos),
    remove: (id: string) => del(`/api/suministros/${id}`),
  },

  conceptos: {
    list: (params: {
      q?: string
      tipo?: string
      activo?: boolean
      limit?: number
      offset?: number
    }) => request<Page<Concepto>>(`/api/conceptos${query(params)}`),
    get: (id: string) => request<ConceptoDetalle>(`/api/conceptos/${id}`),
    create: (datos: Partial<Concepto>) => post<ConceptoDetalle>('/api/conceptos', datos),
    update: (id: string, datos: Partial<Concepto>) =>
      patch<ConceptoDetalle>(`/api/conceptos/${id}`, datos),
    remove: (id: string) => del(`/api/conceptos/${id}`),
    historial: (id: string) => request<RegistroAuditoria[]>(`/api/conceptos/${id}/historial`),
    addLinea: (id: string, datos: { hijo_id: string; rendimiento: string; factor?: string }) =>
      post<Linea>(`/api/conceptos/${id}/lineas`, datos),
    addSuministro: (conceptoId: string, datos: Partial<PrecioSuministro>) =>
      post<PrecioSuministro>(`/api/conceptos/${conceptoId}/suministros`, datos),
    dondeSeUsa: (id: string) => request<UsoCompleto>(`/api/conceptos/${id}/donde-se-usa`),
    historico: (id: string) => request<HistoricoPrecio[]>(`/api/conceptos/${id}/historico-precios`),
    // Vive en el router de facturación (cruza partida + certificación), pero
    // la URL sigue hablando del concepto que el usuario está consultando.
    ventas: (id: string) => request<Ventas>(`/api/conceptos/${id}/ventas`),
    recalcular: (id: string) =>
      post<{ conceptos_modificados: number; ids: string[] }>(
        `/api/conceptos/${id}/recalcular`,
        {},
      ),
  },

  descomposicion: {
    update: (id: string, datos: { rendimiento?: string; factor?: string; orden?: number }) =>
      patch<Linea>(`/api/descomposicion/${id}`, datos),
    remove: (id: string) => del(`/api/descomposicion/${id}`),
  },

  presupuestos: {
    list: (params: {
      q?: string
      estado?: string
      es_plantilla?: boolean
      solo_ultima_version?: boolean
      limit?: number
      offset?: number
    }) => request<Page<PresupuestoResumen>>(`/api/presupuestos${query(params)}`),
    versiones: (id: string) => request<Version[]>(`/api/presupuestos/${id}/versiones`),
    nuevaVersion: (id: string) =>
      post<Presupuesto>(`/api/presupuestos/${id}/nueva-version`, {}),
    comparar: (aId: string, bId: string) =>
      request<Comparacion>(`/api/presupuestos/${aId}/comparar/${bId}`),
    guardarComoPlantilla: (
      id: string,
      datos: { nombre: string; tipo_obra?: string | null; con_mediciones: boolean },
    ) => post<Presupuesto>(`/api/presupuestos/${id}/guardar-como-plantilla`, datos),
    instanciar: (
      id: string,
      datos: { nombre: string; cliente_id?: string | null; emplazamiento?: string | null },
    ) => post<Presupuesto>(`/api/presupuestos/${id}/instanciar`, datos),
    excelUrl: (id: string, opciones: OpcionesExportacion) =>
      `/api/presupuestos/${id}/excel?${queryExportacion(opciones)}`,
    plantillas: (id: string) =>
      request<PlantillaPresupuesto[]>(`/api/presupuestos/${id}/plantillas`),
    plantillaUrl: (id: string, plantillaId: string, formato: 'docx' | 'pdf') =>
      `/api/presupuestos/${id}/plantilla/${plantillaId}?formato=${formato}`,
    get: (id: string) => request<PresupuestoDetalle>(`/api/presupuestos/${id}`),
    create: (datos: Partial<Presupuesto>) => post<Presupuesto>('/api/presupuestos', datos),
    update: (id: string, datos: Partial<Presupuesto>) =>
      patch<Presupuesto>(`/api/presupuestos/${id}`, datos),
    remove: (id: string) => del(`/api/presupuestos/${id}`),
    historial: (id: string) => request<RegistroAuditoria[]>(`/api/presupuestos/${id}/historial`),
    /** Crea de una vez el capítulo + partidas que la IA propuso al leer un
     *  documento, en una sola transacción y con rastro en el historial —
     *  sustituye a llamar `addCapitulo` + `addPartida` en bucle desde el
     *  cliente (ver DocumentoIAModal.confirmarPropuesta). */
    aplicarPropuestaIA: (
      id: string,
      datos: {
        capitulo_resumen: string
        partidas: { resumen: string; unidad: string; precio: string; medicion: string }[]
      },
    ) => post<{ id: string; resumen: string; partidas: number }>(
      `/api/presupuestos/${id}/aplicar-propuesta-ia`,
      datos,
    ),
    /** Como `aplicarPropuestaIA`, pero para partidas con descompuesto real
     *  contra el banco de precios (Fase 42, "Ayuda con IA" proponiendo una
     *  fase de obra entera) en vez de alzadas. */
    aplicarCapituloIA: (
      id: string,
      datos: {
        capitulo_resumen: string
        partidas: {
          partida_id?: string | null
          resumen?: string | null
          unidad?: string | null
          componentes?: {
            concepto_id?: string | null
            rendimiento: string
            personalizado: boolean
            resumen?: string | null
            unidad?: string | null
            precio?: string | null
            naturaleza?: string | null
          }[]
        }[]
      },
    ) => post<{ id: string; resumen: string; partidas: number }>(
      `/api/presupuestos/${id}/aplicar-capitulo-ia`,
      datos,
    ),
    addCapitulo: (
      id: string,
      datos: { resumen: string; parent_id?: string | null; orden?: number },
    ) =>
      post<{ id: string; codigo: string; resumen: string }>(
        `/api/presupuestos/${id}/capitulos`,
        datos,
      ),
    sincronizarPrecios: (id: string) =>
      post<{ partidas_actualizadas: number }>(
        `/api/presupuestos/${id}/sincronizar-precios`,
        {},
      ),
    recursos: (id: string) => request<RecursosPresupuesto>(`/api/presupuestos/${id}/recursos`),
    /** `aplicar: false` solo simula: es lo que alimenta la vista previa (Fase 36). */
    reajustar: (
      id: string,
      datos: { tipo: TipoReajuste; valor: string; aplicar: boolean; metodo?: MetodoCalculo },
    ) => post<Reajuste>(`/api/presupuestos/${id}/reajuste`, datos),
    /** Varios cambios de celda de la rejilla en una sola petición (Fase 33). */
    actualizarLineas: (id: string, cambios: CambioLinea[]) =>
      patch<PresupuestoDetalle>(`/api/presupuestos/${id}/lineas`, { cambios }),
    convertirLinea: (id: string, lineaId: string, tipo: 'capitulo' | 'partida') =>
      post<{ tipo: 'capitulo' | 'partida'; id: string }>(
        `/api/presupuestos/${id}/lineas/${lineaId}/convertir`,
        { tipo },
      ),
    pegarCapitulos: (
      id: string,
      datos: { capitulo_ids: string[]; parent_id?: string | null; alcance: AlcancePegado },
    ) => post<ResultadoPegado>(`/api/presupuestos/${id}/capitulos/pegar`, datos),
  },

  formulasMedicion: {
    list: () => request<FormulaMedicion[]>('/api/formulas-medicion'),
    create: (datos: { nombre: string; expresion: string; descripcion?: string | null }) =>
      post<FormulaMedicion>('/api/formulas-medicion', datos),
    update: (id: string, datos: { nombre?: string; expresion?: string; activa?: boolean }) =>
      patch<FormulaMedicion>(`/api/formulas-medicion/${id}`, datos),
    remove: (id: string) => del(`/api/formulas-medicion/${id}`),
    /** Valida y calcula sin guardar, para ver el resultado al escribirla. */
    probar: (expresion: string, valores: Record<string, string>) =>
      post<{ variables: string[]; resultado: string }>('/api/formulas-medicion/probar', {
        expresion,
        valores,
      }),
  },

  capitulos: {
    update: (
      id: string,
      datos: {
        codigo?: string
        resumen?: string
        texto?: string | null
        orden?: number
        parent_id?: string | null
      },
    ) => patch<{ id: string }>(`/api/capitulos/${id}`, datos),
    remove: (id: string) => del(`/api/capitulos/${id}`),
    addPartida: (
      id: string,
      datos: {
        concepto_id?: string | null
        codigo?: string
        resumen?: string
        unidad?: string
        precio?: string
        orden?: number
        lineas?: { comentario?: string; uds?: string; longitud?: string; anchura?: string; altura?: string }[]
      },
    ) => post<Partida>(`/api/capitulos/${id}/partidas`, datos),
    pegarPartidas: (id: string, datos: { partida_ids: string[]; alcance: AlcancePegado }) =>
      post<ResultadoPegado>(`/api/capitulos/${id}/partidas/pegar`, datos),
  },

  partidas: {
    get: (id: string) => request<PartidaDetalle>(`/api/partidas/${id}`),
    update: (id: string, datos: Partial<Partida>) => patch<Partida>(`/api/partidas/${id}`, datos),
    remove: (id: string) => del(`/api/partidas/${id}`),
    integrarBancoPrecios: (id: string) =>
      post<Partida>(`/api/partidas/${id}/integrar-banco-precios`, {}),
    descomposicion: (id: string) =>
      request<DescomposicionPartida>(`/api/partidas/${id}/descomposicion`),
    anadirComponente: (
      id: string,
      datos: { hijo_id: string; rendimiento?: string; factor?: string },
    ) => post<DescomposicionPartida>(`/api/partidas/${id}/descomposicion`, datos),
    quitarComponente: (id: string, lineaId: string) =>
      del<DescomposicionPartida>(`/api/partidas/${id}/descomposicion/${lineaId}`),
    independizarDescomposicion: (id: string) =>
      post<DescomposicionPartida>(`/api/partidas/${id}/descomposicion/independizar`, {}),
    cambiarPrecioComponente: (
      id: string,
      datos: { hijo_id: string; precio: string; alcance: AlcancePrecio },
    ) =>
      patch<{ partidas_afectadas: number; descomposicion: DescomposicionPartida }>(
        `/api/partidas/${id}/descomposicion/precio`,
        datos,
      ),
    cambiarRendimientoComponente: (id: string, datos: { hijo_id: string; rendimiento: string }) =>
      patch<DescomposicionPartida>(`/api/partidas/${id}/descomposicion/rendimiento`, datos),
    cambiarResumenComponente: (id: string, datos: { hijo_id: string; resumen: string }) =>
      patch<DescomposicionPartida>(`/api/partidas/${id}/descomposicion/resumen`, datos),
    cambiarNaturalezaComponente: (
      id: string,
      datos: { hijo_id: string; naturaleza: NaturalezaConcepto },
    ) => patch<DescomposicionPartida>(`/api/partidas/${id}/descomposicion/naturaleza`, datos),
    cambiarUnidadComponente: (id: string, datos: { hijo_id: string; unidad: string }) =>
      patch<DescomposicionPartida>(`/api/partidas/${id}/descomposicion/unidad`, datos),
    pegarComponentes: (id: string, datos: { linea_ids: string[]; alcance: AlcancePegado }) =>
      post<ResultadoPegado>(`/api/partidas/${id}/descomposicion/pegar`, datos),
    addLinea: (
      id: string,
      datos: {
        comentario?: string | null
        uds?: string | null
        longitud?: string | null
        anchura?: string | null
        altura?: string | null
        orden?: number
        formula_id?: string | null
        formula_valores?: Record<string, string>
      },
    ) => post<LineaMedicion>(`/api/partidas/${id}/lineas`, datos),
    pegarLineas: (id: string, datos: { linea_ids: string[]; alcance: AlcancePegado }) =>
      post<ResultadoPegado>(`/api/partidas/${id}/lineas/pegar`, datos),
  },

  mediciones: {
    update: (
      id: string,
      datos: Partial<LineaMedicion> & { formula_valores?: Record<string, string> },
    ) => patch<LineaMedicion>(`/api/mediciones/${id}`, datos),
    remove: (id: string) => del(`/api/mediciones/${id}`),
  },

  fiebdc: {
    analizar: (fichero: File) => {
      const f = new FormData()
      f.append('fichero', fichero)
      return subir<AnalisisBC3>('/api/fiebdc/analizar', f)
    },
    importar: (
      fichero: File,
      opciones: { estrategia: string; crear_presupuesto: boolean; nombre_presupuesto?: string },
    ) => {
      const f = new FormData()
      f.append('fichero', fichero)
      f.append('estrategia', opciones.estrategia)
      f.append('crear_presupuesto', String(opciones.crear_presupuesto))
      if (opciones.nombre_presupuesto) {
        f.append('nombre_presupuesto', opciones.nombre_presupuesto)
      }
      return subir<ImportacionBC3>('/api/fiebdc/importar', f)
    },
    importarEnCapitulo: (capituloId: string, fichero: File, estrategia: string) => {
      const f = new FormData()
      f.append('fichero', fichero)
      f.append('estrategia', estrategia)
      return subir<ImportacionBC3>(`/api/fiebdc/importar-en-capitulo/${capituloId}`, f)
    },
    importarEnPresupuesto: (presupuestoId: string, fichero: File, estrategia: string) => {
      const f = new FormData()
      f.append('fichero', fichero)
      f.append('estrategia', estrategia)
      return subir<ImportacionBC3>(`/api/fiebdc/importar-en-presupuesto/${presupuestoId}`, f)
    },
    exportarUrl: (presupuestoId: string, opciones: OpcionesExportacion) =>
      `/api/fiebdc/exportar/${presupuestoId}?${queryExportacion(opciones)}`,
  },

  personal: {
    list: (params: { activo?: boolean; limit?: number; offset?: number }) =>
      request<Page<Personal>>(`/api/personal${query(params)}`),
    create: (datos: Partial<Personal>) => post<Personal>('/api/personal', datos),
    update: (id: string, datos: Partial<Personal>) =>
      patch<Personal>(`/api/personal/${id}`, datos),
    remove: (id: string) => del(`/api/personal/${id}`),
  },

  obras: {
    list: (params: { estado?: string; limit?: number; offset?: number }) =>
      request<Page<ObraResumen>>(`/api/obras${query(params)}`),
    get: (id: string) => request<ObraDetalle>(`/api/obras/${id}`),
    create: (datos: { nombre: string; presupuesto_id: string; fecha_inicio?: string | null }) =>
      post<Obra>('/api/obras', datos),
    update: (id: string, datos: Partial<Obra>) => patch<Obra>(`/api/obras/${id}`, datos),
    remove: (id: string) => del(`/api/obras/${id}`),
    historial: (id: string) => request<RegistroAuditoria[]>(`/api/obras/${id}/historial`),
    asignaciones: (id: string) =>
      request<AsignacionDetalle[]>(`/api/obras/${id}/asignaciones`),
    addAsignacion: (
      id: string,
      datos: { personal_id: string; fecha_desde: string; coste_hora?: string | null },
    ) => post<Asignacion>(`/api/obras/${id}/asignaciones`, datos),
    costes: (id: string) => request<InformeCosteObra>(`/api/obras/${id}/costes`),
  },

  asignaciones: {
    get: (id: string) => request<AsignacionDetalle>(`/api/asignaciones/${id}`),
    remove: (id: string) => del(`/api/asignaciones/${id}`),
    addParte: (
      id: string,
      datos: { fecha: string; horas: string; capitulo_id?: string | null; notas?: string | null },
    ) => post<ParteTrabajo>(`/api/asignaciones/${id}/partes`, datos),
  },

  partesTrabajo: {
    remove: (id: string) => del(`/api/partes-trabajo/${id}`),
  },

  albaranes: {
    list: (params: { obra_id?: string; proveedor_id?: string; limit?: number; offset?: number }) =>
      request<Page<AlbaranResumen>>(`/api/albaranes${query(params)}`),
    get: (id: string) => request<AlbaranDetalle>(`/api/albaranes/${id}`),
    create: (datos: {
      obra_id: string
      proveedor_id: string
      numero_proveedor?: string | null
      fecha: string
      lineas?: {
        concepto_id?: string | null
        capitulo_id?: string | null
        descripcion?: string | null
        unidad?: string | null
        cantidad: string
        precio_unitario?: string | null
      }[]
    }) => post<AlbaranDetalle>('/api/albaranes', datos),
    update: (id: string, datos: Partial<Albaran>) => patch<Albaran>(`/api/albaranes/${id}`, datos),
    remove: (id: string) => del(`/api/albaranes/${id}`),
    addLinea: (
      id: string,
      datos: {
        concepto_id?: string | null
        capitulo_id?: string | null
        descripcion?: string | null
        unidad?: string | null
        cantidad: string
        precio_unitario?: string | null
      },
    ) => post<AlbaranLinea>(`/api/albaranes/${id}/lineas`, datos),
  },

  albaranesLineas: {
    remove: (id: string) => del(`/api/albaranes-lineas/${id}`),
  },

  certificaciones: {
    list: (params: { obra_id?: string; limit?: number; offset?: number }) =>
      request<Page<Certificacion>>(`/api/certificaciones${query(params)}`),
    get: (id: string) => request<CertificacionDetalle>(`/api/certificaciones/${id}`),
    create: (datos: {
      obra_id: string
      fecha: string
      retencion_garantia_pct?: string
      lineas: { partida_id: string; medicion_actual: string }[]
    }) => post<CertificacionDetalle>('/api/certificaciones', datos),
    update: (id: string, datos: { fecha?: string; retencion_garantia_pct?: string; notas?: string | null }) =>
      patch<CertificacionDetalle>(`/api/certificaciones/${id}`, datos),
    remove: (id: string) => del(`/api/certificaciones/${id}`),
    historial: (id: string) =>
      request<RegistroAuditoria[]>(`/api/certificaciones/${id}/historial`),
    emitir: (id: string) => post<CertificacionDetalle>(`/api/certificaciones/${id}/emitir`, {}),
    generarFactura: (id: string, datos: { concepto?: string; serie?: string; fecha_vencimiento?: string | null }) =>
      post<Factura>(`/api/certificaciones/${id}/factura`, datos),
    pdfUrl: (id: string) => `/api/certificaciones/${id}/pdf`,
  },

  facturas: {
    list: (params: { obra_id?: string; estado?: string; limit?: number; offset?: number }) =>
      request<Page<FacturaResumen>>(`/api/facturas${query(params)}`),
    get: (id: string) => request<FacturaDetalle>(`/api/facturas/${id}`),
    createSuelta: (datos: {
      obra_id: string
      cliente_id?: string | null
      concepto: string
      base_imponible: string
      tipo_iva?: TipoIVA
      inversion_sujeto_pasivo?: boolean
      serie?: string | null
      fecha_vencimiento?: string | null
    }) => post<Factura>('/api/facturas', datos),
    update: (id: string, datos: { concepto?: string; fecha_vencimiento?: string | null; notas?: string | null }) =>
      patch<Factura>(`/api/facturas/${id}`, datos),
    remove: (id: string) => del(`/api/facturas/${id}`),
    historial: (id: string) => request<RegistroAuditoria[]>(`/api/facturas/${id}/historial`),
    emitir: (id: string) => post<Factura>(`/api/facturas/${id}/emitir`, {}),
    anular: (id: string, motivo: string) => post<Factura>(`/api/facturas/${id}/anular`, { motivo }),
    notificar: (id: string) => post<Factura>(`/api/facturas/${id}/notificar`, {}),
    pdfUrl: (id: string) => `/api/facturas/${id}/pdf`,
    addCobro: (id: string, datos: { fecha: string; importe: string; forma_pago?: string | null; notas?: string | null }) =>
      post<Cobro>(`/api/facturas/${id}/cobros`, datos),
  },

  cobros: {
    remove: (id: string) => del(`/api/cobros/${id}`),
  },

  ia: {
    estadisticas: (tipo_obra?: string) =>
      request<Estadisticas>(`/api/ia/estadisticas${query({ tipo_obra })}`),
    sugerencias: (params: { limit?: number; offset?: number } = {}) =>
      request<Page<Sugerencia>>(`/api/ia/sugerencias${query(params)}`),
    solicitar: (datos: { tipo_obra: string; descripcion?: string | null }) =>
      post<SugerenciaDetalle>('/api/ia/sugerencias', datos),
    get: (id: string) => request<SugerenciaDetalle>(`/api/ia/sugerencias/${id}`),
    crearPlantilla: (
      id: string,
      datos: {
        nombre: string
        codigo?: string | null
        capitulos: {
          resumen: string
          partidas: { concepto_id?: string | null; resumen: string; unidad: string }[]
        }[]
      },
    ) => post<Presupuesto>(`/api/ia/sugerencias/${id}/plantilla`, datos),
    mediciones: {
      leer: (partidaId: string, fichero: File) => {
        const formulario = new FormData()
        formulario.append('partida_id', partidaId)
        formulario.append('fichero', fichero)
        return subir<LecturaPlanoDetalle>('/api/ia/mediciones', formulario)
      },
      get: (id: string) => request<LecturaPlanoDetalle>(`/api/ia/mediciones/${id}`),
      aplicar: (
        id: string,
        lineas: {
          comentario?: string | null
          uds?: string | null
          longitud?: string | null
          anchura?: string | null
          altura?: string | null
        }[],
      ) => post<LineaMedicion[]>(`/api/ia/mediciones/${id}/aplicar`, { lineas }),
    },
    ayudaLineaConversar: (datos: {
      contexto: {
        tipo: 'capitulo' | 'partida'
        codigo?: string | null
        resumen: string
        unidad?: string | null
        precio?: string | null
        presupuesto_id: string
        presupuesto_nombre: string
      }
      mensajes: { rol: 'user' | 'assistant'; contenido: string }[]
    }) => post<{ respuesta: string; propuesta: PropuestaIA | null }>('/api/ia/ayuda-linea/conversar', datos),
    documentoConversar: (
      ficheros: File[],
      mensajes: { rol: 'user' | 'assistant'; contenido: string }[],
      presupuestoId?: string,
    ) => {
      const f = new FormData()
      for (const fichero of ficheros) f.append('ficheros', fichero)
      f.append('mensajes', JSON.stringify(mensajes))
      if (presupuestoId) f.append('presupuesto_id', presupuestoId)
      return subir<{ respuesta: string; propuesta: PropuestaIA | null }>(
        '/api/ia/documentos/conversar',
        f,
      )
    },
    previsualizarExcel: (fichero: File) => {
      const f = new FormData()
      f.append('fichero', fichero)
      return subir<{ tabla: string }>('/api/ia/documentos/previsualizar-excel', f)
    },
  },
}

export const ETIQUETA_ESTADO_CERTIFICACION: Record<EstadoCertificacion, string> = {
  borrador: 'Borrador',
  emitida: 'Emitida',
}

export const ETIQUETA_ESTADO_FACTURA: Record<EstadoFactura, string> = {
  borrador: 'Borrador',
  emitida: 'Emitida',
  anulada: 'Anulada',
}

export const ETIQUETA_SITUACION_COBRO: Record<SituacionCobro, string> = {
  pendiente: 'Pendiente',
  parcial: 'Cobro parcial',
  cobrada: 'Cobrada',
  '-': '—',
}

export const ETIQUETA_ESTADO_OBRA: Record<EstadoObra, string> = {
  planificada: 'Planificada',
  en_ejecucion: 'En ejecución',
  paralizada: 'Paralizada',
  finalizada: 'Finalizada',
  cerrada: 'Cerrada',
}

export const ETIQUETA_ESTADO_ALBARAN: Record<EstadoAlbaran, string> = {
  borrador: 'Borrador',
  conformado: 'Conformado',
  facturado: 'Facturado',
}

export const ETIQUETA_ESTADO: Record<EstadoPresupuesto, string> = {
  borrador: 'Borrador',
  emitido: 'Emitido',
  aprobado: 'Aprobado',
  rechazado: 'Rechazado',
  cancelado: 'Cancelado',
}

export const ETIQUETA_TIPO_CONCEPTO: Record<TipoConcepto, string> = {
  basico: 'Básico',
  auxiliar: 'Auxiliar',
  unitario: 'Unitario',
}

export const ETIQUETA_NATURALEZA: Record<NaturalezaConcepto, string> = {
  sin_clasificar: 'Sin clasificar',
  mano_obra: 'Mano de obra',
  maquinaria: 'Maquinaria',
  material: 'Material',
  servicio: 'Servicio',
  residuo: 'Residuo',
  otro: 'Otro',
}

export const ETIQUETA_ORIGEN_PRECIO: Record<OrigenPrecio, string> = {
  manual: 'Manual',
  producto: 'Tarifa de proveedor',
  descomposicion: 'Calculado',
}

export const ETIQUETA_IVA: Record<TipoIVA, string> = {
  general: 'General (21 %)',
  reducido: 'Reducido (10 %)',
  superreducido: 'Superreducido (4 %)',
  exento: 'Exento',
}

export const ETIQUETA_FORMA_PAGO: Record<FormaPago, string> = {
  transferencia: 'Transferencia',
  domiciliado: 'Domiciliado',
  pagare: 'Pagaré',
  confirming: 'Confirming',
  efectivo: 'Efectivo',
  tarjeta: 'Tarjeta',
}
