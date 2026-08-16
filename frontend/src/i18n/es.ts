/** Bundle base (español) de textos de interfaz — Fase 19.
 *
 * Cada cuenta puede reescribir cualquier clave desde Ajustes > Traducción
 * (`api.ajustes.traduccion`); ese override se funde sobre este bundle al
 * arrancar la sesión (`workspace.tsx`), vía `i18n.addResourceBundle`. Este
 * fichero es SOLO el valor por defecto — nunca se edita por cuenta.
 *
 * Se extraen pantallas por lotes: lo que todavía no está aquí sigue con
 * texto literal en su `.tsx`, y se va migrando en fases sucesivas.
 */
export const es = {
  comun: {
    guardar: 'Guardar',
    guardando: 'Guardando…',
    cancelar: 'Cancelar',
    crear: 'Crear',
    creando: 'Creando…',
    eliminar: 'Eliminar',
    volver: 'Volver',
    abrir: 'Abrir',
    activo: 'Activo',
    sinDefinir: 'Sin definir',
    errorDesconocido: 'Error desconocido',
    sinResultados: 'Sin resultados',
    sinResultadosConFiltros: 'Sin resultados con estos filtros',
  },
  nav: {
    salir: 'Salir',
    plataforma: 'Plataforma',
    grupoOrganizacion: 'Organización',
    grupoAdministracion: 'Administración',
    usuariosYGrupos: 'Usuarios y grupos',
    cuentas: 'Cuentas',
    tarifas: 'Tarifas',
    personalPlataforma: 'Personal de la plataforma',
    ajustes: 'Ajustes',
    abrirMenu: 'Abrir menú',
    ocultarMenu: 'Ocultar menú',
    mostrarMenu: 'Mostrar menú',
    ajustesDe: 'Ajustes de {{modulo}}',
  },
  ajustes: {
    titulo: 'Ajustes',
    descripcion: 'Configuración de la organización: módulos, y los ajustes propios de cada uno.',
    modulos: {
      titulo: 'Módulos',
      descripcionHub: 'Activa o desactiva los módulos de la organización.',
      descripcionPantalla:
        'Cada módulo es independiente y se activa por organización. Activar uno arrastra sus dependencias; no se puede desactivar un módulo del que dependan otros activos.',
      volverAAjustes: 'Volver a Ajustes',
      siempreActivo: 'Siempre activo',
      desactivar: 'Desactivar',
      activar: 'Activar',
      nucleo: 'núcleo',
      requiere: 'requiere: {{modulos}}',
    },
    ajustesDeModulo: {
      titulo: 'Ajustes de módulo',
      moduloNoEncontrado: 'Módulo no encontrado',
      moduloNoEncontradoDesc: 'No está activo en esta organización o no existe.',
      sinAjustesPropios: 'Sin ajustes propios todavía',
      sinAjustesPropiosDesc: 'Este módulo no tiene todavía ninguna opción configurable.',
    },
    numeracion: {
      titulo: 'Numeración',
      nota: 'El código interno de cada presupuesto, albarán y factura — no la serie/número fiscal de las facturas, que sigue siempre las reglas legales de Veri*Factu. Tokens disponibles: {{seq}} el correlativo, {{fecha}} la fecha, {{org}} el identificador de la organización.',
      secuenciaCompartida: 'Secuencia compartida entre las organizaciones de esta cuenta',
      avisoCifsDistintos:
        'Las organizaciones de esta cuenta tienen CIF distinto: compartir el correlativo entre ellas puede no cumplir la correlatividad exigida a cada empresa por separado — es tu decisión, no lo bloqueamos.',
      guardado: 'Patrón de {{tipo}} guardado',
      tipoPresupuesto: 'Presupuestos',
      tipoAlbaran: 'Albaranes de compra',
      tipoFactura: 'Facturas (código interno)',
    },
    diccionario: {
      titulo: 'Diccionario',
      descripcionHub: 'Países, formas de pago y otras listas de referencia de la cuenta.',
      descripcionPantalla: 'Listas de referencia de la cuenta, compartidas por todas sus organizaciones.',
      paises: 'Países',
      formasDePago: 'Formas de pago',
      provincias: 'Provincias',
      unidadesMedida: 'Unidades de medida',
      formasJuridicas: 'Formas jurídicas',
      tratamientos: 'Tratamiento',
      cargos: 'Cargo / puesto',
      iva: 'IVA',
      recargoEquivalencia: 'Recargo de equivalencia',
      retenciones: 'Retenciones',
      valor: 'Valor (%)',
      notaIva:
        'Solo de referencia: el % legal que se aplica de verdad en presupuestos y facturas sigue fijo en el motor de cálculo, para no romper el IVA de un documento ya emitido.',
      notaRecargo:
        'Solo de referencia por ahora: aplicarlo automáticamente en una línea es una fase futura.',
      notaRetencion:
        'Valores habituales para elegir rápido en la ficha del tercero — el campo sigue admitiendo cualquier porcentaje.',
      buscar: 'Buscar por clave o etiqueta…',
      nuevaEntrada: 'Nueva entrada',
      clave: 'Clave',
      claveHint: 'Identificador interno, no se puede cambiar luego',
      etiqueta: 'Etiqueta',
      guardadoToast: '«{{etiqueta}}» guardado',
      confirmarEliminar: '¿Eliminar «{{etiqueta}}»?',
    },
    traduccion: {
      titulo: 'Traducción',
      descripcionHub: 'Personaliza cualquier texto de la interfaz a tu gusto.',
      descripcionPantalla:
        'Reescribe cualquier texto de la interfaz. Lo que no se toca aquí se muestra con su valor de fábrica.',
      buscar: 'Buscar por clave o texto…',
      clave: 'Clave',
      valorPorDefecto: 'Valor de fábrica',
      tuTexto: 'Tu texto',
      restablecer: 'Restablecer',
      personalizado: 'Personalizado',
      guardadoToast: 'Traducción guardada',
      restablecidoToast: 'Restablecido al valor de fábrica',
    },
    camposLibres: {
      titulo: 'Campos libres',
      descripcionHub: 'Campos propios sobre terceros, productos, obras, presupuestos y sus líneas.',
    },
  },
  terceros: {
    titulo: 'Terceros',
    descripcion: 'Clientes, proveedores y subcontratistas en una sola ficha con roles.',
    nuevo: 'Nuevo tercero',
    sinTerceros: 'Sin terceros todavía',
    creaElPrimero: 'Crea el primero para empezar.',
    columnaCodigo: 'Código',
    columnaRazonSocial: 'Razón social',
    columnaNif: 'NIF',
    columnaRoles: 'Roles',
    columnaPoblacion: 'Población',
    columnaPago: 'Pago',
    rolCliente: 'Cliente',
    rolProveedor: 'Proveedor',
    rolSubcontratista: 'Subcontratista',
    inactivo: 'inactivo',
    razonSocial: 'Razón social',
    nifCif: 'NIF / CIF',
    nifCifHint: 'Se valida el dígito de control',
    poblacion: 'Población',
  },
} as const

export type RecursosI18n = typeof es
