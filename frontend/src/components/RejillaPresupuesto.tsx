import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeftRight,
  Boxes,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Clipboard,
  Copy,
  ExternalLink,
  FolderPlus,
  Layers,
  Lock,
  LockOpen,
  Plus,
  Ruler,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'

import { AyudaIAModal } from './AyudaIAModal'
import { BotonAtajos } from './AtajosTeclado'
import { BuscadorSustitutoModal } from './BuscadorSustitutoModal'
import { DocumentoIAModal } from './DocumentoIAModal'
import { ImportarBC3EnCapituloModal } from './ImportarBC3EnCapituloModal'
import { PegarModal } from './PegarModal'
import type { ColumnaRejilla, ItemMenuContextual, OpcionCelda } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { AlcancePegado, CambioLinea, NodoCapitulo, Partida, PresupuestoDetalle } from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'
import { copiarAlPortapapeles, leerPortapapeles } from '../lib/portapapeles'
import { useToast } from '../toast'
import { useWorkspace } from '../workspace'

/** Una línea de la rejilla: capítulos y partidas aplanados en una sola lista,
 *  que es como se teclea un presupuesto de verdad (y como lo enseñan Presto y
 *  cualquier hoja de cálculo). El árbol se reconstruye por `nivel`. */
export interface FilaPresupuesto {
  id: string
  tipo: 'capitulo' | 'partida'
  nivel: number
  codigo: string
  resumen: string
  /** Descripción con formato del capítulo (HTML). Para la partida, la suya
   *  vive en `partida.texto` — este campo solo se rellena para capítulos. */
  texto: string | null
  unidad: string
  medicion: string
  precio: string
  importe: string
  conceptoId: string | null
  /** Capítulo contenedor (de la partida) o capítulo padre (del capítulo). */
  padreId: string | null
  orden: number
  tieneDesglose: boolean
  precioVenta: string
  ventaBloqueada: boolean
  importeVenta: string
  estadoVenta: 'perdida' | 'bajo' | 'ok'
  partida?: Partida
}

/** Fila sintética que representa al presupuesto entero, para poder
 *  pegar/arrastrar a nivel raíz igual que a cualquier otro capítulo — hasta
 *  ahora la raíz no tenía ninguna fila propia a la que apuntar. No es un
 *  capítulo real: no se puede editar, borrar ni copiar, y su "capítulo
 *  contenedor" es `null` de verdad (ver `contenedorDe`). */
export const ID_RAIZ = '__raiz__'

function construirFilas(p: {
  codigo: string
  nombre: string
  capitulos: NodoCapitulo[]
}): FilaPresupuesto[] {
  const raiz: FilaPresupuesto = {
    id: ID_RAIZ,
    tipo: 'capitulo',
    nivel: 0,
    codigo: p.codigo,
    resumen: p.nombre,
    texto: null,
    unidad: '',
    medicion: '',
    precio: '',
    importe: String(p.capitulos.reduce((s, c) => s + Number(c.importe), 0)),
    conceptoId: null,
    padreId: null,
    orden: -1,
    tieneDesglose: false,
    precioVenta: '',
    ventaBloqueada: false,
    importeVenta: String(p.capitulos.reduce((s, c) => s + Number(c.importe_venta), 0)),
    estadoVenta: 'ok',
  }
  // OJO: el tercer argumento sigue siendo `null`, no `ID_RAIZ` — `padreId` es
  // el `parent_id` real de backend (lo que lee `indentar`/`contenedorDe` para
  // escribir), y un capítulo de verdad a nivel raíz lo sigue teniendo a
  // `null`. Solo `nivel` (puramente visual) se desplaza, para que se vea
  // anidado bajo esta fila sintética.
  return [raiz, ...aplanar(p.capitulos, 1, null)]
}

function aplanar(capitulos: NodoCapitulo[], nivel = 0, padreId: string | null = null): FilaPresupuesto[] {
  const filas: FilaPresupuesto[] = []
  for (const capitulo of capitulos) {
    filas.push({
      id: capitulo.id,
      tipo: 'capitulo',
      nivel,
      codigo: capitulo.codigo,
      resumen: capitulo.resumen,
      texto: capitulo.texto,
      unidad: '',
      medicion: '',
      precio: '',
      importe: capitulo.importe,
      conceptoId: null,
      padreId,
      orden: capitulo.orden,
      tieneDesglose: false,
      precioVenta: '',
      ventaBloqueada: false,
      importeVenta: capitulo.importe_venta,
      estadoVenta: 'ok',
    })
    for (const partida of capitulo.partidas) {
      filas.push({
        id: partida.id,
        tipo: 'partida',
        nivel: nivel + 1,
        codigo: partida.codigo,
        resumen: partida.resumen,
        texto: partida.texto,
        unidad: partida.unidad,
        medicion: partida.medicion,
        precio: partida.precio,
        importe: partida.importe,
        conceptoId: partida.concepto_id,
        padreId: capitulo.id,
        orden: partida.orden,
        tieneDesglose: partida.tiene_desglose,
        precioVenta: partida.precio_venta,
        ventaBloqueada: partida.venta_bloqueada,
        importeVenta: partida.importe_venta,
        estadoVenta: partida.estado_venta,
        partida,
      })
    }
    filas.push(...aplanar(capitulo.hijos, nivel + 1, capitulo.id))
  }
  return filas
}

const RETARDO_GUARDADO = 700

export function RejillaPresupuesto({
  presupuesto,
  onCambio,
  onMedir,
  onIntegrarBanco,
  onSeleccionar,
  seleccionadaId,
}: {
  presupuesto: PresupuestoDetalle
  onCambio: () => void
  onMedir: (partida: Partida) => void
  onIntegrarBanco: (partida: Partida) => void
  onSeleccionar?: (fila: FilaPresupuesto | null) => void
  seleccionadaId?: string | null
}) {
  const { notificar } = useToast()
  const { modules } = useWorkspace()
  const iaActiva = modules.some((m) => m.code === 'ia' && m.is_active)
  const unidadesMedida = useDiccionario('unidad_medida')
  const [filas, setFilas] = useState<FilaPresupuesto[]>(() => construirFilas(presupuesto))
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [pendiente, setPendiente] = useState(false)
  const [replegados, setReplegados] = useState<Set<string>>(new Set())
  const [filtros, setFiltros] = useState<Record<string, string>>({})
  const [pegando, setPegando] = useState<{
    tipo: 'partidas' | 'capitulos'
    ids: string[]
    origenEtiqueta: string
    /** Capítulo destino de unas partidas (nunca `null`), o padre de unos
     *  capítulos (`null` = raíz del presupuesto). */
    destino: string | null
  } | null>(null)
  const [ayudaIA, setAyudaIA] = useState<FilaPresupuesto | null>(null)
  // «Cambiar por banco de precios» (Fase 52): solo tiene sentido sobre una
  // partida (no un capítulo) — un capítulo no tiene ni resumen ni precio
  // propio con qué buscar un sustituto.
  const [sustituyendo, setSustituyendo] = useState<FilaPresupuesto | null>(null)
  // "Arrastrar al presupuesto": BC3 se cuelga de un capítulo, o de la raíz
  // del presupuesto (`capituloId: null`) como capítulos de primer nivel;
  // PDF/imagen abre la conversación con la IA. `filaParaSubir` es del botón
  // "Subir fichero…" del menú contextual, la alternativa sin arrastrar — el
  // input de fichero en sí está oculto y se dispara con `.click()`.
  const [importandoBc3, setImportandoBc3] = useState<{
    ficheros: File[]
    capituloId: string | null
    capituloResumen: string
  } | null>(null)
  const [documentoIA, setDocumentoIA] = useState<{
    ficheros: File[]
    // Si se soltó/pidió sobre una partida existente, la IA además puede
    // proponerle mediciones directamente (Fase 51c) en vez de solo crear
    // capítulos nuevos.
    partidaId: string | null
  } | null>(null)
  const inputFicheroRef = useRef<HTMLInputElement>(null)
  const filaParaSubir = useRef<FilaPresupuesto | null>(null)
  const cambios = useRef<Map<string, CambioLinea>>(new Map())
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Para saber dónde pegar (Ctrl+V): el capítulo de la fila con el cursor
  // encima en ese momento, que `onSeleccionar` va actualizando a cada
  // movimiento — no vale `seleccionadaId`, que sigue a la fila que la ficha
  // externa tiene abierta y puede ir por libre.
  const filaActiva = useRef<FilaPresupuesto | null>(null)

  const filasDelServidor = useMemo(() => construirFilas(presupuesto), [presupuesto])

  // Un capítulo se puede replegar para no perderse en un presupuesto largo. Se
  // oculta todo lo que cuelgue de él, a cualquier profundidad: se sube por la
  // cadena de padres y basta con que uno esté replegado.
  const porId = useMemo(() => new Map(filas.map((f) => [f.id, f])), [filas])
  const conHijos = useMemo(
    () => new Set(filas.map((f) => f.padreId).filter((x): x is string => Boolean(x))),
    [filas],
  )
  const ocultaPorAncestro = (fila: FilaPresupuesto) => {
    let padre = fila.padreId
    while (padre) {
      if (replegados.has(padre)) return true
      padre = porId.get(padre)?.padreId ?? null
    }
    return false
  }

  // Un valor "en bruto" por columna y fila, para filtrar sin depender de
  // `columnas` (definida más abajo, con acceso a `unidadesMedida`) — mismos
  // campos que sus `valor()`, sin formatear.
  function valorCrudoDe(f: FilaPresupuesto, columnaId: string): string {
    switch (columnaId) {
      case 'tipo':
        return f.id === ID_RAIZ
          ? 'presupuesto'
          : f.tipo === 'capitulo'
            ? 'capitulo'
            : f.conceptoId
              ? 'unitaria'
              : 'alzada'
      case 'codigo':
        return f.codigo
      case 'resumen':
        return f.resumen
      case 'unidad':
        return f.tipo === 'partida' ? f.unidad : ''
      case 'medicion':
        return f.tipo === 'partida' ? f.medicion : ''
      case 'precio':
        return f.tipo === 'partida' ? f.precio : ''
      case 'importe':
        return f.importe
      case 'precio_venta':
        return f.tipo === 'partida' ? f.precioVenta : ''
      case 'importe_venta':
        return f.importeVenta
      default:
        return ''
    }
  }

  // Filtros por columna (Fase 1f): una fila pasa si coincide con TODOS los
  // filtros activos a la vez. Un capítulo que coincide enseña todo lo que
  // cuelga de él (para eso se filtraba); una fila que coincide enseña
  // también la cadena de capítulos que la contienen, para no dejarla
  // huérfana sin contexto. Mientras se filtra, se ignoran los capítulos
  // replegados a mano — si no, un acierto podría quedar oculto sin explicación.
  const filtrosActivos = Object.entries(filtros).filter(([, v]) => v.trim() !== '')
  const filtrando = filtrosActivos.length > 0
  const idsCoincidentes = useMemo(() => {
    if (!filtrando) return null
    const activos = filtrosActivos.map(([id, v]) => [id, v.trim().toLowerCase()] as const)
    const ids = new Set<string>()
    const hijosDe = new Map<string, FilaPresupuesto[]>()
    for (const f of filas) {
      if (!f.padreId) continue
      const lista = hijosDe.get(f.padreId)
      if (lista) lista.push(f)
      else hijosDe.set(f.padreId, [f])
    }
    const marcarDescendientes = (id: string) => {
      for (const hijo of hijosDe.get(id) ?? []) {
        if (ids.has(hijo.id)) continue
        ids.add(hijo.id)
        if (hijo.tipo === 'capitulo') marcarDescendientes(hijo.id)
      }
    }
    for (const f of filas) {
      const coincide = activos.every(([id, q]) => valorCrudoDe(f, id).toLowerCase().includes(q))
      if (!coincide) continue
      ids.add(f.id)
      let padre = f.padreId
      while (padre) {
        ids.add(padre)
        padre = porId.get(padre)?.padreId ?? null
      }
      if (f.tipo === 'capitulo') marcarDescendientes(f.id)
    }
    return ids
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtrando, filtros, filas, porId])

  const filasVisibles = filas.filter((f) =>
    filtrando ? (idsCoincidentes?.has(f.id) ?? false) : !ocultaPorAncestro(f),
  )

  // Totales de coste y venta: siempre a partir de las partidas (nunca de los
  // capítulos, que ya son la suma de las suyas — sumarlos también sería
  // contar dos veces). Con un filtro activo, el total es el de lo
  // encontrado; si no, el del presupuesto entero, colapsado o no.
  const totales = useMemo(() => {
    let coste = 0
    let venta = 0
    for (const f of filas) {
      if (f.tipo !== 'partida') continue
      if (filtrando && !idsCoincidentes?.has(f.id)) continue
      coste += Number(f.importe)
      venta += Number(f.importeVenta)
    }
    return { coste, venta }
  }, [filas, filtrando, idsCoincidentes])

  function alternarReplegado(id: string) {
    setReplegados((previos) => {
      const nuevos = new Set(previos)
      if (nuevos.has(id)) nuevos.delete(id)
      else nuevos.add(id)
      return nuevos
    })
  }

  const replegarTodo = () =>
    setReplegados(new Set(filas.filter((f) => conHijos.has(f.id)).map((f) => f.id)))
  const expandirTodo = () => setReplegados(new Set())

  // El servidor manda la verdad (códigos renumerados, importes, totales). Solo
  // se pisa el estado local si no hay nada por guardar: si no, se perdería lo
  // que el usuario acaba de teclear y aún no ha salido.
  useEffect(() => {
    if (cambios.current.size === 0) setFilas(filasDelServidor)
  }, [filasDelServidor])

  const volcar = useCallback(async () => {
    if (cambios.current.size === 0) return
    const tanda = [...cambios.current.values()]
    cambios.current.clear()
    setPendiente(false)
    setGuardando(true)
    try {
      const actualizado = await api.presupuestos.actualizarLineas(presupuesto.id, tanda)
      setFilas(construirFilas(actualizado))
      setError(null)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }, [presupuesto.id, onCambio])

  // Guardar lo que quede al desmontar: cerrar la ficha con cambios en el aire
  // los perdería.
  useEffect(() => {
    return () => {
      if (temporizador.current) clearTimeout(temporizador.current)
      void volcar()
    }
  }, [volcar])

  function encolar(fila: FilaPresupuesto, campo: keyof CambioLinea, valor: string | boolean) {
    const clave = `${fila.tipo}:${fila.id}`
    const previo = cambios.current.get(clave) ?? { id: fila.id, tipo: fila.tipo }
    cambios.current.set(clave, { ...previo, [campo]: valor })
    setPendiente(true)
    if (temporizador.current) clearTimeout(temporizador.current)
    temporizador.current = setTimeout(() => void volcar(), RETARDO_GUARDADO)
  }

  function editarLocal(id: string, cambio: Partial<FilaPresupuesto>) {
    setFilas((actuales) => actuales.map((f) => (f.id === id ? { ...f, ...cambio } : f)))
  }

  async function alEditar(fila: FilaPresupuesto, columnaId: string, valor: string, opcion?: OpcionCelda) {
    if (columnaId === 'tipo') {
      await cambiarTipo(fila, valor)
      return
    }

    // Elegir un concepto del banco desde la descripción: la partida pasa a ser
    // unitaria y se trae código, unidad y precio del cuadro.
    if (columnaId === 'resumen' && opcion && !opcion.esAccion && fila.tipo === 'partida') {
      try {
        const concepto = await api.conceptos.get(opcion.valor)
        await api.partidas.update(fila.id, {
          concepto_id: concepto.id,
          codigo: concepto.codigo,
          resumen: concepto.resumen,
          unidad: concepto.unidad,
          precio: concepto.precio,
          // La descripción ampliada no viaja sola como el descompuesto (que
          // se hereda en vivo del banco hasta que se independiza, ver
          // `descomposicion_de_partida`): `texto` es un campo propio de la
          // partida sin ese enlace, así que si no se copia aquí, al elegir
          // un concepto la partida se queda con la descripción vacía —
          // igual que ya se copian código/resumen/unidad/precio.
          texto: concepto.texto,
        })
        onCambio()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido')
      }
      return
    }

    if (columnaId === 'resumen' && opcion?.esAccion && fila.tipo === 'partida') {
      await crearEnBanco(fila, opcion.valor)
      return
    }

    if (columnaId === 'precio_venta') {
      // Escribir una venta a mano la da por pactada: se bloquea sola, que es
      // lo que evita que el siguiente reajuste de porcentajes la borre.
      editarLocal(fila.id, { precioVenta: valor, ventaBloqueada: true })
      encolar(fila, 'precio_venta', valor)
      encolar(fila, 'venta_bloqueada', true)
      return
    }

    const campo = columnaId as keyof CambioLinea
    editarLocal(fila.id, { [columnaId]: valor } as Partial<FilaPresupuesto>)
    encolar(fila, campo, valor)
  }

  async function cambiarTipo(fila: FilaPresupuesto, destino: string) {
    setError(null)
    try {
      if (destino === 'alzada') {
        if (fila.tipo !== 'partida') return
        await api.partidas.update(fila.id, { concepto_id: null })
        notificar('Partida suelta del banco de precios')
        onCambio()
        return
      }
      if (destino === 'unitaria') {
        if (fila.conceptoId) return
        notificar('Escribe en Descripción y elige un concepto del banco para hacerla unitaria')
        return
      }
      if (destino === 'capitulo' && fila.tipo === 'capitulo') return
      if (destino === 'partida' && fila.tipo === 'partida') return

      await api.presupuestos.convertirLinea(
        presupuesto.id,
        fila.id,
        destino === 'capitulo' ? 'capitulo' : 'partida',
      )
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function crearEnBanco(fila: FilaPresupuesto, resumen: string) {
    try {
      const concepto = await api.conceptos.create({
        resumen,
        unidad: fila.unidad || 'ud',
        precio: fila.precio || '0',
        tipo: 'unitario',
      })
      await api.partidas.update(fila.id, {
        concepto_id: concepto.id,
        codigo: concepto.codigo,
        resumen: concepto.resumen,
      })
      notificar(`«${resumen}» dado de alta en el banco de precios`)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  /** Orden para colocar una línea nueva al final de su contenedor. */
  function siguienteOrden(padreId: string | null, tipo: 'capitulo' | 'partida'): number {
    const hermanos = filas.filter((f) => f.padreId === padreId && f.tipo === tipo)
    return hermanos.reduce((maximo, f) => Math.max(maximo, f.orden), -1) + 1
  }

  async function nuevaFila(actual: FilaPresupuesto | null) {
    setError(null)
    try {
      // Sin nada todavía, o desde la fila raíz: lo primero que hace falta es
      // un capítulo.
      if (!actual || actual.id === ID_RAIZ) {
        await api.presupuestos.addCapitulo(presupuesto.id, { resumen: 'Nuevo capítulo' })
        onCambio()
        return
      }
      const capituloId = actual.tipo === 'capitulo' ? actual.id : actual.padreId
      if (!capituloId) return
      // Va al final del capítulo: sin esto todas nacerían con orden 0 y la
      // línea nueva aparecería arriba, no debajo de donde estabas.
      const orden = siguienteOrden(capituloId, 'partida')
      // El backend no admite partidas sin descripción (una alzada sin texto no
      // se puede identificar). Se crea con un texto de arranque que el usuario
      // sobrescribe: al entrar en la celda queda seleccionado entero.
      await api.capitulos.addPartida(capituloId, { resumen: 'Nueva partida', orden })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function nuevoCapitulo(actual: FilaPresupuesto | null) {
    setError(null)
    try {
      const parentId = actual?.padreId ?? null
      await api.presupuestos.addCapitulo(presupuesto.id, {
        resumen: 'Nuevo capítulo',
        parent_id: parentId,
        orden: siguienteOrden(parentId, 'capitulo'),
      })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function alternarCandado(fila: FilaPresupuesto) {
    setError(null)
    try {
      await api.partidas.update(fila.id, { venta_bloqueada: !fila.ventaBloqueada })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminarFila(fila: FilaPresupuesto) {
    if (fila.id === ID_RAIZ) return
    const que = fila.tipo === 'capitulo' ? 'el capítulo y todo su contenido' : 'la partida'
    if (!window.confirm(`¿Eliminar ${que} «${fila.resumen || fila.codigo}»?`)) return
    try {
      if (fila.tipo === 'capitulo') await api.capitulos.remove(fila.id)
      else await api.partidas.remove(fila.id)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  /** El capítulo que contiene a una fila: el suyo propio si es un capítulo,
   *  el de su padre si es una partida. Sirve tanto de destino para pegar
   *  partidas (que siempre necesitan un capítulo) como de padre para pegar
   *  capítulos (que además admiten `null`: raíz del presupuesto). */
  function contenedorDe(fila: FilaPresupuesto | null): string | null {
    if (!fila) return null
    if (fila.id === ID_RAIZ) return null
    return fila.tipo === 'capitulo' ? fila.id : fila.padreId
  }

  function copiar(ids: string[]) {
    const filas = ids
      .map((id) => porId.get(id))
      .filter((f): f is FilaPresupuesto => f != null && f.id !== ID_RAIZ)
    if (filas.length === 0) return
    // Una marca puede mezclar capítulos y partidas; se copia solo el tipo de
    // la primera fila arrastrada o marcada, no una mezcla de las dos —el
    // portapapeles es de un solo tipo a la vez.
    const tipo = filas[0].tipo
    const mismos = filas.filter((f) => f.tipo === tipo).map((f) => f.id)
    if (tipo === 'capitulo') {
      copiarAlPortapapeles({ tipo: 'capitulos', ids: mismos, origenEtiqueta: presupuesto.nombre })
      notificar(mismos.length === 1 ? 'Capítulo copiado' : `${mismos.length} capítulos copiados`)
    } else {
      copiarAlPortapapeles({ tipo: 'partidas', ids: mismos, origenEtiqueta: presupuesto.nombre })
      notificar(mismos.length === 1 ? 'Partida copiada' : `${mismos.length} partidas copiadas`)
    }
  }

  /** Ctrl+V usa la fila con el cursor encima (`filaActiva`); soltar un
   *  arrastre (Fase 1d) manda la fila sobre la que se soltó en su lugar —
   *  puede ser distinta de la que tenía el foco de teclado. */
  function pegar(filaDestino?: FilaPresupuesto | null) {
    const contenido = leerPortapapeles()
    if (!contenido) {
      notificar('No hay nada copiado')
      return
    }
    // `null` explícito (soltar en la franja de la raíz, ver RejillaEditable)
    // tiene que valer como "la raíz", no como "sin especificar" — con `??`
    // los dos casos se confundían y `null` acababa cayendo en
    // `filaActiva.current`, el mismo bug que ya arreglaba `pegarEnRaiz` para
    // el atajo de teclado, pero sin cubrir todavía soltar arrastrando.
    const actual = filaDestino !== undefined ? filaDestino : filaActiva.current
    const destino = contenedorDe(actual)
    if (contenido.tipo === 'partidas') {
      if (!destino) {
        notificar('Selecciona antes un capítulo, o una partida dentro de uno, para pegar ahí')
        return
      }
      setPegando({ tipo: 'partidas', ids: contenido.ids, origenEtiqueta: contenido.origenEtiqueta, destino })
      return
    }
    if (contenido.tipo === 'capitulos') {
      // `destino` puede ser `null` aquí a propósito: sin fila activa, el
      // capítulo se pega a nivel raíz del presupuesto.
      setPegando({ tipo: 'capitulos', ids: contenido.ids, origenEtiqueta: contenido.origenEtiqueta, destino })
      return
    }
    notificar('Lo copiado no se puede pegar aquí')
  }

  /** Soltar cerca del borde de una fila (Fase 1i): reordenar como hermano
   *  suyo, justo antes o después — a diferencia de `pegar` (soltar "dentro"),
   *  esto siempre es un movimiento sin preguntar copiar/mover, porque
   *  reordenar solo tiene sentido moviendo lo que ya había. Si lo que se
   *  arrastra es de otro tipo que la fila de destino (una partida sobre el
   *  borde de un capítulo, por ejemplo), no hay hermandad posible — cae al
   *  comportamiento normal de `pegar`. */
  function soltarEnBorde(filaDestino: FilaPresupuesto, zona: 'antes' | 'despues') {
    const contenido = leerPortapapeles()
    if (!contenido) {
      notificar('No hay nada copiado')
      return
    }
    const tipoArrastrado = contenido.tipo === 'capitulos' ? 'capitulo' : contenido.tipo === 'partidas' ? 'partida' : null
    if (tipoArrastrado !== filaDestino.tipo) {
      pegar(filaDestino)
      return
    }
    void reordenarComoHermano(contenido.ids, filaDestino, zona)
  }

  async function reordenarComoHermano(
    idsArrastrados: string[],
    filaDestino: FilaPresupuesto,
    zona: 'antes' | 'despues',
  ) {
    const tipo = filaDestino.tipo
    const contenedor = filaDestino.padreId
    const idsArrastradosSet = new Set(idsArrastrados)

    const hermanos = filas
      .filter((f) => f.id !== ID_RAIZ && f.tipo === tipo && f.padreId === contenedor && !idsArrastradosSet.has(f.id))
      .sort((a, b) => a.orden - b.orden)

    const indiceDestino = hermanos.findIndex((f) => f.id === filaDestino.id)
    if (indiceDestino === -1) return
    const posicion = zona === 'antes' ? indiceDestino : indiceDestino + 1

    const listaFinal = [
      ...hermanos.slice(0, posicion).map((f) => f.id),
      ...idsArrastrados,
      ...hermanos.slice(posicion).map((f) => f.id),
    ]

    try {
      await Promise.all(
        listaFinal.map((id, indice) => {
          const origen = porId.get(id)
          const cambiaDeContenedor = Boolean(origen) && origen!.padreId !== contenedor
          if (tipo === 'capitulo') {
            return api.capitulos.update(id, {
              orden: indice,
              ...(cambiaDeContenedor ? { parent_id: contenedor } : {}),
            })
          }
          // Una partida siempre tiene contenedor (su capítulo): `tipo === 'partida'`
          // nunca llega aquí con `contenedor` a `null` (ver `aplanar`).
          return api.partidas.update(id, {
            orden: indice,
            ...(cambiaDeContenedor && contenedor ? { capitulo_id: contenedor } : {}),
          })
        }),
      )
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  /** Pegar a nivel raíz sin depender de qué fila esté activa: con contenido
   *  ya en la rejilla, `filaActiva` casi nunca es `null` (queda pegada a lo
   *  último que se tocó), así que `pegar()` nunca resolvía sola la raíz —
   *  hacía falta este atajo explícito. Solo tiene sentido para capítulos: una
   *  partida no puede vivir sin uno. */
  function pegarEnRaiz() {
    const contenido = leerPortapapeles()
    if (!contenido) {
      notificar('No hay nada copiado')
      return
    }
    if (contenido.tipo !== 'capitulos') {
      notificar('Solo se puede pegar un capítulo a nivel raíz')
      return
    }
    setPegando({
      tipo: 'capitulos',
      ids: contenido.ids,
      origenEtiqueta: contenido.origenEtiqueta,
      destino: null,
    })
  }

  async function confirmarPegado(alcance: AlcancePegado) {
    if (!pegando) return
    try {
      const resultado =
        pegando.tipo === 'partidas'
          ? await api.capitulos.pegarPartidas(pegando.destino!, { partida_ids: pegando.ids, alcance })
          : await api.presupuestos.pegarCapitulos(presupuesto.id, {
              capitulo_ids: pegando.ids,
              parent_id: pegando.destino,
              alcance,
            })
      setPegando(null)
      onCambio()
      if (resultado.pegadas === 0) {
        notificar('No se pegó nada: ¿un capítulo soltado sobre sí mismo o uno de sus propios subcapítulos?')
        return
      }
      notificar(
        pegando.tipo === 'partidas'
          ? resultado.pegadas === 1
            ? '1 partida pegada'
            : `${resultado.pegadas} partidas pegadas`
          : resultado.pegadas === 1
            ? '1 capítulo pegado'
            : `${resultado.pegadas} capítulos pegados`,
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setPegando(null)
    }
  }

  /** BC3 se cuelga del capítulo (el suyo si `fila` ya es uno, si no el de su
   *  padre — mismo criterio que `contenedorDe`), o de la raíz del presupuesto
   *  si se suelta ahí (`contenedorDe` da `null`); PDF/imagen/Excel no
   *  necesita capítulo, solo el presupuesto, así que hasta la fila raíz vale.
   *  Se puede soltar más de un fichero a la vez (Fase 41): los BC3 se
   *  importan uno detrás de otro en el mismo modal, y los documentos se
   *  adjuntan todos juntos a una sola conversación con la IA. */
  function manejarFicheros(fila: FilaPresupuesto, archivos: File[]) {
    const bc3: File[] = []
    const docs: File[] = []
    const rechazados: string[] = []
    for (const archivo of archivos) {
      const nombre = archivo.name.toLowerCase()
      const esBc3 = nombre.endsWith('.bc3')
      const esPdf = archivo.type === 'application/pdf' || nombre.endsWith('.pdf')
      const esImagen = archivo.type.startsWith('image/')
      const esExcel = nombre.endsWith('.xlsx')
      if (esBc3) bc3.push(archivo)
      else if (esPdf || esImagen || esExcel) docs.push(archivo)
      else rechazados.push(archivo.name)
    }

    if (bc3.length > 0) {
      const capituloId = contenedorDe(fila)
      const capitulo = capituloId ? (fila.tipo === 'capitulo' ? fila : porId.get(capituloId)) : null
      setImportandoBc3({ ficheros: bc3, capituloId, capituloResumen: capitulo?.resumen ?? '' })
    }
    if (docs.length > 0) {
      setDocumentoIA({ ficheros: docs, partidaId: fila.tipo === 'partida' ? fila.id : null })
    }
    if (rechazados.length > 0) {
      notificar(
        `No se puede soltar aquí: ${rechazados.join(', ')} (solo BC3, PDF, imagen o Excel)`,
      )
    }
  }

  function pedirFichero(fila: FilaPresupuesto) {
    filaParaSubir.current = fila
    inputFicheroRef.current?.click()
  }

  function menuContextualDe(f: FilaPresupuesto): ItemMenuContextual[] {
    const esRaiz = f.id === ID_RAIZ
    const items: ItemMenuContextual[] = [
      {
        id: 'pegar',
        etiqueta: esRaiz ? 'Pegar en la raíz' : 'Pegar',
        icono: <Clipboard size={14} aria-hidden="true" />,
        onClick: () => pegar(f),
        disabled: !leerPortapapeles(),
      },
    ]
    if (!esRaiz) {
      items.unshift({
        id: 'copiar',
        etiqueta: f.tipo === 'capitulo' ? 'Copiar capítulo' : 'Copiar partida',
        icono: <Copy size={14} aria-hidden="true" />,
        onClick: () => copiar([f.id]),
      })
    }
    if (f.tipo === 'partida' && f.conceptoId) {
      items.push({
        id: 'banco',
        etiqueta: 'Abrir en banco de precios',
        icono: <ExternalLink size={14} aria-hidden="true" />,
        onClick: () => window.open(`/banco-precios/${f.conceptoId}`, '_blank'),
      })
    }
    if (f.tipo === 'partida') {
      items.push({
        id: 'sustituir',
        etiqueta: 'Cambiar por banco de precios…',
        icono: <ArrowLeftRight size={14} aria-hidden="true" />,
        onClick: () => setSustituyendo(f),
      })
    }
    if (iaActiva) {
      items.push({
        id: 'ia',
        etiqueta: 'Ayuda con IA',
        icono: <Sparkles size={14} aria-hidden="true" />,
        onClick: () => setAyudaIA(f),
      })
    }
    items.push({
      id: 'subir-fichero',
      etiqueta: 'Subir fichero (BC3, PDF o imagen)…',
      icono: <Upload size={14} aria-hidden="true" />,
      onClick: () => pedirFichero(f),
    })
    return items
  }

  /** Alt+→ / Alt+←: mueve la línea un nivel dentro del árbol. */
  async function indentar(fila: FilaPresupuesto, direccion: 1 | -1) {
    if (fila.id === ID_RAIZ) return
    setError(null)
    const indice = filas.findIndex((f) => f.id === fila.id)
    try {
      if (direccion === 1) {
        // Colgar de la línea anterior que pueda ser su contenedor. La fila
        // raíz nunca vale como contenedor real: no tiene un `id` de verdad.
        const anterior = [...filas.slice(0, indice)]
          .reverse()
          .find((f) => f.tipo === 'capitulo' && f.id !== fila.id && f.id !== ID_RAIZ)
        if (!anterior) return
        if (fila.tipo === 'partida') await api.partidas.update(fila.id, { capitulo_id: anterior.id })
        else await api.capitulos.update(fila.id, { parent_id: anterior.id })
      } else {
        // Subir un nivel: pasar a colgar del abuelo.
        const padre = filas.find((f) => f.id === fila.padreId)
        if (!padre) return
        if (fila.tipo === 'partida') {
          if (!padre.padreId) return
          await api.partidas.update(fila.id, { capitulo_id: padre.padreId })
        } else {
          await api.capitulos.update(fila.id, { parent_id: padre.padreId })
        }
      }
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const columnas: ColumnaRejilla<FilaPresupuesto>[] = [
    {
      id: 'tipo',
      etiqueta: 'Tipo',
      ancho: '120px',
      tipo: 'select',
      valor: (f) =>
        f.id === ID_RAIZ
          ? 'presupuesto'
          : f.tipo === 'capitulo'
            ? 'capitulo'
            : f.conceptoId
              ? 'unitaria'
              : 'alzada',
      editable: (f) => f.id !== ID_RAIZ,
      opciones: () => [
        { valor: 'capitulo', etiqueta: 'Capítulo' },
        { valor: 'unitaria', etiqueta: 'Unitaria' },
        { valor: 'alzada', etiqueta: 'Alzada' },
      ],
    },
    {
      id: 'codigo',
      etiqueta: 'Código',
      ancho: '170px',
      valor: (f) => f.codigo,
      editable: (f) => f.id !== ID_RAIZ,
      sangrada: true,
      prefijo: (f) =>
        f.tipo === 'capitulo' && conHijos.has(f.id) ? (
          <button
            className="rejilla__plegar"
            aria-label={replegados.has(f.id) ? `Expandir ${f.resumen}` : `Replegar ${f.resumen}`}
            // El clic es del desplegable, no de la celda: sin esto el cursor
            // saltaría aquí y encima entraría en edición al segundo clic.
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              alternarReplegado(f.id)
            }}
          >
            {replegados.has(f.id) ? (
              <ChevronRight size={14} aria-hidden="true" />
            ) : (
              <ChevronDown size={14} aria-hidden="true" />
            )}
          </button>
        ) : null,
    },
    {
      id: 'resumen',
      etiqueta: 'Descripción',
      // Sin ancho fijo, `table-layout: fixed` le daba solo lo que sobraba
      // tras repartir las demás columnas — a veces apenas 20px. Con esto,
      // si no cabe todo, el widget scrollea en horizontal antes que
      // aplastar justo la columna que hay que poder leer.
      ancho: '260px',
      valor: (f) => f.resumen,
      editable: (f) => f.id !== ID_RAIZ,
      tipo: 'autocompletado',
      buscar: async (q, fila) => {
        if (fila.tipo === 'capitulo' || q.trim().length < 2) return []
        const pagina = await api.conceptos.list({ q, tipo: 'unitario', activo: true, limit: 8 })
        const sugerencias: OpcionCelda[] = pagina.items.map((c) => ({
          valor: c.id,
          etiqueta: `${c.codigo} · ${c.resumen}`,
          detalle: `${formatoImporte(c.precio)} €/${c.unidad}`,
        }))
        sugerencias.push({
          valor: q,
          etiqueta: `Crear «${q}» en el banco de precios`,
          esAccion: true,
        })
        return sugerencias
      },
      // Iconos de aviso, no de acción: se ven de un vistazo qué partidas
      // llevan descompuesto propio o mediciones detalladas, sin entrar en
      // cada una para comprobarlo.
      prefijo: (f) => {
        if (f.tipo !== 'partida' || !f.partida) return null
        const avisos: { icono: typeof Boxes; texto: string }[] = []
        if (f.partida.descomposicion_propia) {
          avisos.push({ icono: Boxes, texto: 'Tiene descompuesto propio' })
        }
        if (f.tieneDesglose) {
          avisos.push({ icono: Ruler, texto: 'Tiene mediciones detalladas' })
        }
        if (avisos.length === 0) return null
        return (
          <span className="rejilla__avisos">
            {avisos.map(({ icono: Icono, texto }) => (
              <Tooltip key={texto} texto={texto}>
                <Icono size={12} aria-hidden="true" className="rejilla__aviso" />
              </Tooltip>
            ))}
          </span>
        )
      },
    },
    {
      id: 'unidad',
      etiqueta: 'Ud.',
      ancho: '100px',
      tipo: 'select',
      valor: (f) => f.unidad,
      editable: (f) => f.tipo === 'partida',
      opciones: () => unidadesMedida.map((u) => ({ valor: u.clave, etiqueta: u.etiqueta })),
    },
    {
      id: 'medicion',
      etiqueta: 'Medición',
      ancho: '110px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'partida' ? formatoImporte(f.medicion, 3) : ''),
      // Con desglose, la medición es la suma de los parciales: se edita en el
      // panel de mediciones, no aquí.
      editable: (f) => f.tipo === 'partida' && !f.tieneDesglose,
    },
    {
      id: 'precio',
      etiqueta: 'Precio',
      ancho: '110px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'partida' ? formatoImporte(f.precio) : ''),
      editable: (f) => f.tipo === 'partida',
    },
    {
      id: 'importe',
      etiqueta: 'Coste',
      ancho: '110px',
      tipo: 'numero',
      valor: (f) => formatoImporte(f.importe),
      total: `${formatoImporte(String(totales.coste))} €`,
    },
    {
      id: 'precio_venta',
      etiqueta: 'Venta',
      ancho: '120px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'partida' ? formatoImporte(f.precioVenta) : ''),
      editable: (f) => f.tipo === 'partida',
    },
    {
      id: 'importe_venta',
      etiqueta: 'Importe venta',
      ancho: '130px',
      tipo: 'numero',
      // Sin gatear a partida: igual que "Coste", en un capítulo es la suma
      // de lo que cuelgue de él, a cualquier profundidad.
      valor: (f) => formatoImporte(f.importeVenta),
      total: `${formatoImporte(String(totales.venta))} €`,
    },
  ]

  return (
    <>
      <div className="rejilla-barra">
        <BotonAtajos
          conAutocompletado
          extra={[{ teclas: 'Alt+→ / Alt+←', hace: 'Meter o sacar la línea de un capítulo' }]}
        />
        {conHijos.size > 0 && (
          <>
            <Tooltip texto="Replegar todos los capítulos">
              <button
                className="btn btn--sm btn--solo-icono"
                aria-label="Replegar todos los capítulos"
                onClick={replegarTodo}
              >
                <ChevronsDownUp size={14} aria-hidden="true" />
              </button>
            </Tooltip>
            <Tooltip texto="Expandir todos los capítulos">
              <button
                className="btn btn--sm btn--solo-icono"
                aria-label="Expandir todos los capítulos"
                onClick={expandirTodo}
              >
                <ChevronsUpDown size={14} aria-hidden="true" />
              </button>
            </Tooltip>
          </>
        )}
        <Tooltip texto="Pegar el capítulo copiado a nivel raíz del presupuesto (no dentro de otro)">
          <button className="btn btn--sm btn--solo-icono" aria-label="Pegar en la raíz" onClick={pegarEnRaiz}>
            <Clipboard size={14} aria-hidden="true" />
          </button>
        </Tooltip>
        <span className="rejilla-barra__estado">
          {guardando ? (
            <span className="muted">Guardando…</span>
          ) : pendiente ? (
            <span className="muted">Sin guardar…</span>
          ) : (
            <span className="muted">Guardado</span>
          )}
        </span>
        <Tooltip texto="Añadir un capítulo al mismo nivel">
          <button className="btn btn--sm" onClick={() => void nuevoCapitulo(null)}>
            <FolderPlus size={14} aria-hidden="true" />
            Capítulo
          </button>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={filasVisibles}
        columnas={columnas}
        idDe={(f) => f.id}
        nivelDe={(f) => f.nivel}
        claseDe={(f) =>
          f.id === ID_RAIZ
            ? 'fila-capitulo fila-raiz'
            : f.tipo === 'capitulo'
              ? 'fila-capitulo'
              : `venta-${f.estadoVenta}`
        }
        onEditar={(f, col, valor, opcion) => void alEditar(f, col, valor, opcion)}
        onNuevaFila={nuevaFila}
        onEliminarFila={(f) => void eliminarFila(f)}
        onIndentar={(f, d) => void indentar(f, d)}
        onSeleccionar={(f) => {
          filaActiva.current = f
          onSeleccionar?.(f)
        }}
        seleccionadaId={seleccionadaId}
        onCopiar={copiar}
        onPegar={pegar}
        onSoltarEn={(f, zona) => (f && zona !== 'dentro' ? soltarEnBorde(f, zona) : pegar(f))}
        puedeArrastrar={(f) => f.id !== ID_RAIZ}
        onSoltarFichero={manejarFicheros}
        menuContextual={menuContextualDe}
        menuVacio={() => [
          {
            id: 'pegar-raiz',
            etiqueta: 'Pegar en la raíz',
            icono: <Clipboard size={14} aria-hidden="true" />,
            onClick: pegarEnRaiz,
            disabled: leerPortapapeles()?.tipo !== 'capitulos',
          },
        ]}
        filtros={filtros}
        onFiltrar={(columnaId, valor) => setFiltros((f) => ({ ...f, [columnaId]: valor }))}
        vacia={
          filtrando ? (
            <EmptyState title="Sin resultados">Nada coincide con los filtros.</EmptyState>
          ) : (
            <EmptyState title="Presupuesto vacío">
              Empieza creando un capítulo; dentro irán las partidas con su medición.
              <div style={{ marginTop: 'var(--sp-3)' }}>
                <button className="btn" onClick={() => void nuevoCapitulo(null)}>
                  <FolderPlus size={16} aria-hidden="true" />
                  Añadir capítulo
                </button>
              </div>
            </EmptyState>
          )
        }
        acciones={(f) =>
          f.tipo === 'partida' && f.partida ? (
            <>
              {f.conceptoId === null && (
                <>
                  <Tooltip texto="Dar de alta esta partida en el banco de precios">
                    <button
                      className="btn btn--sm btn--solo-icono"
                      aria-label="Añadir al banco de precios"
                      onClick={() => onIntegrarBanco(f.partida!)}
                    >
                      <Layers size={14} aria-hidden="true" />
                    </button>
                  </Tooltip>{' '}
                </>
              )}
              <Tooltip
                texto={
                  f.ventaBloqueada
                    ? 'Venta bloqueada: un reajuste no la moverá. Pulsa para desbloquear'
                    : 'Venta calculada. Pulsa para bloquearla'
                }
              >
                <button
                  className={
                    f.ventaBloqueada
                      ? 'btn btn--sm btn--solo-icono is-bloqueada'
                      : 'btn btn--sm btn--solo-icono'
                  }
                  aria-label={f.ventaBloqueada ? 'Desbloquear la venta' : 'Bloquear la venta'}
                  onClick={() => void alternarCandado(f)}
                >
                  {f.ventaBloqueada ? (
                    <Lock size={14} aria-hidden="true" />
                  ) : (
                    <LockOpen size={14} aria-hidden="true" />
                  )}
                </button>
              </Tooltip>{' '}
              <Tooltip texto="Desglosar la medición">
                <button
                  className="btn btn--sm btn--solo-icono"
                  aria-label="Desglosar la medición"
                  onClick={() => onMedir(f.partida!)}
                >
                  <Ruler size={14} aria-hidden="true" />
                </button>
              </Tooltip>{' '}
              <Tooltip texto="Eliminar esta partida">
                <button
                  className="btn btn--sm btn--danger btn--solo-icono"
                  aria-label="Eliminar esta partida"
                  onClick={() => void eliminarFila(f)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            </>
          ) : f.id === ID_RAIZ ? (
            <Tooltip texto="Añadir un capítulo">
              <button
                className="btn btn--sm btn--solo-icono"
                aria-label="Añadir un capítulo"
                onClick={() => void nuevaFila(f)}
              >
                <Plus size={14} aria-hidden="true" />
              </button>
            </Tooltip>
          ) : (
            <>
              <Tooltip texto="Añadir una partida en este capítulo">
                <button
                  className="btn btn--sm btn--solo-icono"
                  aria-label="Añadir una partida en este capítulo"
                  onClick={() => void nuevaFila(f)}
                >
                  <Plus size={14} aria-hidden="true" />
                </button>
              </Tooltip>{' '}
              <Tooltip texto="Eliminar este capítulo y su contenido">
                <button
                  className="btn btn--sm btn--danger btn--solo-icono"
                  aria-label="Eliminar este capítulo"
                  onClick={() => void eliminarFila(f)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            </>
          )
        }
      />

      {/* Alternativa sin arrastrar al "Arrastrar al presupuesto" del menú
          contextual — oculto, lo dispara `pedirFichero` con `.click()`. */}
      <input
        ref={inputFicheroRef}
        type="file"
        multiple
        accept=".bc3,.xlsx,application/pdf,image/png,image/jpeg,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          const archivos = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (archivos.length > 0 && filaParaSubir.current) {
            manejarFicheros(filaParaSubir.current, archivos)
          }
        }}
      />

      {pegando && (
        <PegarModal
          cantidad={pegando.ids.length}
          origenEtiqueta={pegando.origenEtiqueta}
          onElegir={(alcance) => void confirmarPegado(alcance)}
          onClose={() => setPegando(null)}
        />
      )}

      {ayudaIA && (
        <AyudaIAModal
          contexto={{
            tipo: ayudaIA.tipo,
            codigo: ayudaIA.codigo || null,
            resumen: ayudaIA.resumen,
            unidad: ayudaIA.tipo === 'partida' ? ayudaIA.unidad : null,
            precio: ayudaIA.tipo === 'partida' ? ayudaIA.precio : null,
            presupuesto_id: presupuesto.id,
            presupuesto_nombre: presupuesto.nombre,
          }}
          destinoCapituloId={contenedorDe(ayudaIA)}
          onCambio={onCambio}
          onClose={() => setAyudaIA(null)}
        />
      )}

      {importandoBc3 && (
        <ImportarBC3EnCapituloModal
          ficheros={importandoBc3.ficheros}
          presupuestoId={presupuesto.id}
          capituloId={importandoBc3.capituloId}
          capituloResumen={importandoBc3.capituloResumen}
          onImportado={() => {
            // Lo que acaba de traer el BC3 es autoritativo: aunque hubiera
            // una edición local a medio teclear en otra celda, que gane el
            // servidor — si no, la sincronización de más abajo (línea ~337)
            // la deja esperando a que esa edición se guarde sola, y hasta
            // entonces el capítulo/partida nuevo no aparece en la rejilla.
            cambios.current.clear()
            onCambio()
          }}
          onClose={() => setImportandoBc3(null)}
        />
      )}

      {documentoIA && (
        <DocumentoIAModal
          ficheros={documentoIA.ficheros}
          entidad="presupuesto"
          entidadId={presupuesto.id}
          presupuestoId={presupuesto.id}
          partidaId={documentoIA.partidaId}
          onClose={() => setDocumentoIA(null)}
          onCambio={() => {
            cambios.current.clear()
            onCambio()
          }}
        />
      )}
      {sustituyendo && (
        <BuscadorSustitutoModal
          resumenActual={sustituyendo.resumen}
          unidadActual={sustituyendo.unidad}
          modo="partida"
          excluirPartidaId={sustituyendo.id}
          onAplicar={async (candidato, copiarDescompuesto) => {
            await api.partidas.sustituir(sustituyendo.id, {
              origen: candidato.origen,
              concepto_id: candidato.concepto_id,
              partida_origen_id: candidato.partida_id,
              copiar_descompuesto: copiarDescompuesto,
            })
            cambios.current.clear()
            onCambio()
            notificar(`«${sustituyendo.resumen}» sustituida por «${candidato.resumen}»`)
          }}
          onClose={() => setSustituyendo(null)}
        />
      )}
    </>
  )
}
