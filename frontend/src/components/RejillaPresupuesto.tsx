import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Boxes,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  FolderPlus,
  Layers,
  Lock,
  LockOpen,
  Plus,
  Ruler,
  Trash2,
} from 'lucide-react'

import { BotonAtajos } from './AtajosTeclado'
import { PegarModal } from './PegarModal'
import type { ColumnaRejilla, OpcionCelda } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { AlcancePegado, CambioLinea, NodoCapitulo, Partida, PresupuestoDetalle } from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'
import { copiarAlPortapapeles, leerPortapapeles } from '../lib/portapapeles'
import { useToast } from '../toast'

/** Una línea de la rejilla: capítulos y partidas aplanados en una sola lista,
 *  que es como se teclea un presupuesto de verdad (y como lo enseñan Presto y
 *  cualquier hoja de cálculo). El árbol se reconstruye por `nivel`. */
export interface FilaPresupuesto {
  id: string
  tipo: 'capitulo' | 'partida'
  nivel: number
  codigo: string
  resumen: string
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

function aplanar(capitulos: NodoCapitulo[], nivel = 0, padreId: string | null = null): FilaPresupuesto[] {
  const filas: FilaPresupuesto[] = []
  for (const capitulo of capitulos) {
    filas.push({
      id: capitulo.id,
      tipo: 'capitulo',
      nivel,
      codigo: capitulo.codigo,
      resumen: capitulo.resumen,
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
      importeVenta: '',
      estadoVenta: 'ok',
    })
    for (const partida of capitulo.partidas) {
      filas.push({
        id: partida.id,
        tipo: 'partida',
        nivel: nivel + 1,
        codigo: partida.codigo,
        resumen: partida.resumen,
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
  const unidadesMedida = useDiccionario('unidad_medida')
  const [filas, setFilas] = useState<FilaPresupuesto[]>(() => aplanar(presupuesto.capitulos))
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [pendiente, setPendiente] = useState(false)
  const [replegados, setReplegados] = useState<Set<string>>(new Set())
  const [pegando, setPegando] = useState<{
    ids: string[]
    origenEtiqueta: string
    capituloId: string
  } | null>(null)
  const cambios = useRef<Map<string, CambioLinea>>(new Map())
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Para saber dónde pegar (Ctrl+V): el capítulo de la fila con el cursor
  // encima en ese momento, que `onSeleccionar` va actualizando a cada
  // movimiento — no vale `seleccionadaId`, que sigue a la fila que la ficha
  // externa tiene abierta y puede ir por libre.
  const filaActiva = useRef<FilaPresupuesto | null>(null)

  const filasDelServidor = useMemo(() => aplanar(presupuesto.capitulos), [presupuesto])

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
  const filasVisibles = filas.filter((f) => !ocultaPorAncestro(f))

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
      setFilas(aplanar(actualizado.capitulos))
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
      // Sin nada todavía, lo primero que hace falta es un capítulo.
      if (!actual) {
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

  function copiarPartidas(ids: string[]) {
    // Solo partidas: copiar un capítulo entero (con sus partidas) no es lo
    // que pide la Fase 1b, así que si hay capítulos marcados junto a
    // partidas se descartan en silencio en vez de fallar todo el copiado.
    const partidas = ids.filter((id) => porId.get(id)?.tipo === 'partida')
    if (partidas.length === 0) {
      notificar('Marca una o varias partidas para copiar')
      return
    }
    copiarAlPortapapeles({
      tipo: 'partidas',
      ids: partidas,
      origenEtiqueta: presupuesto.nombre,
    })
    notificar(partidas.length === 1 ? 'Partida copiada' : `${partidas.length} partidas copiadas`)
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
    if (contenido.tipo !== 'partidas') {
      notificar('Lo copiado no se puede pegar aquí')
      return
    }
    const actual = filaDestino ?? filaActiva.current
    const capituloId = actual ? (actual.tipo === 'capitulo' ? actual.id : actual.padreId) : null
    if (!capituloId) {
      notificar('Selecciona antes un capítulo, o una partida dentro de uno, para pegar ahí')
      return
    }
    setPegando({ ids: contenido.ids, origenEtiqueta: contenido.origenEtiqueta, capituloId })
  }

  async function confirmarPegado(alcance: AlcancePegado) {
    if (!pegando) return
    try {
      const resultado = await api.capitulos.pegarPartidas(pegando.capituloId, {
        partida_ids: pegando.ids,
        alcance,
      })
      setPegando(null)
      onCambio()
      notificar(resultado.pegadas === 1 ? 'Partida pegada' : `${resultado.pegadas} partidas pegadas`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setPegando(null)
    }
  }

  /** Alt+→ / Alt+←: mueve la línea un nivel dentro del árbol. */
  async function indentar(fila: FilaPresupuesto, direccion: 1 | -1) {
    setError(null)
    const indice = filas.findIndex((f) => f.id === fila.id)
    try {
      if (direccion === 1) {
        // Colgar de la línea anterior que pueda ser su contenedor.
        const anterior = [...filas.slice(0, indice)]
          .reverse()
          .find((f) => f.tipo === 'capitulo' && f.id !== fila.id)
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
        f.tipo === 'capitulo' ? 'capitulo' : f.conceptoId ? 'unitaria' : 'alzada',
      editable: () => true,
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
      editable: () => true,
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
      editable: () => true,
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
      valor: (f) => (f.tipo === 'partida' ? formatoImporte(f.importeVenta) : ''),
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
          f.tipo === 'capitulo' ? 'fila-capitulo' : `venta-${f.estadoVenta}`
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
        onCopiar={copiarPartidas}
        onPegar={pegar}
        onSoltarEn={(f) => pegar(f)}
        puedeArrastrar={(f) => f.tipo === 'partida'}
        vacia={
          <EmptyState title="Presupuesto vacío">
            Empieza creando un capítulo; dentro irán las partidas con su medición.
            <div style={{ marginTop: 'var(--sp-3)' }}>
              <button className="btn" onClick={() => void nuevoCapitulo(null)}>
                <FolderPlus size={16} aria-hidden="true" />
                Añadir capítulo
              </button>
            </div>
          </EmptyState>
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

      {pegando && (
        <PegarModal
          cantidad={pegando.ids.length}
          origenEtiqueta={pegando.origenEtiqueta}
          onElegir={(alcance) => void confirmarPegado(alcance)}
          onClose={() => setPegando(null)}
        />
      )}
    </>
  )
}
