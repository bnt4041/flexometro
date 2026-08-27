/** El árbol de la obra: capítulos, partidas y medición real.
 *
 *  Hermana de `RejillaPresupuesto` pero no la misma: son tablas distintas y el
 *  trabajo es otro. Aquí no hay banco de precios ni descompuestos — en obra se
 *  mide lo ejecutado, no se presupuesta contra un catálogo. Lo que sí hay y
 *  allí no es la **procedencia**: de qué presupuesto salió cada línea, y si
 *  entró después de arrancar (anexo o adenda).
 *
 *  Arrastrar documentos y "pedir a la IA" (misma operativa que en
 *  presupuestos, `DocumentoIAModal`) también existen aquí, pero acotados a lo
 *  que la obra puede representar: solo partidas alzadas con precio directo
 *  (`proponer_importar_capitulo`) o mediciones para una partida ya existente
 *  — nunca un descompuesto contra el banco, que la obra no tiene.
 *
 *  Lo que se reutiliza tal cual es `RejillaEditable`, que es UI pura, y el
 *  patrón de guardado por tandas con retardo: se teclea seguido y se manda una
 *  sola vez. Los campos se mandan de uno en uno a propósito — encolar la fila
 *  entera hacía que una edición pisara la anterior recién guardada.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlignLeft,
  Boxes,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  FolderPlus,
  GitBranch,
  Plus,
  Ruler,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'

import { api } from '../lib/api'
import type { ArbolObra, NodoObra, PartidaObra } from '../lib/api'
import { DocumentoIAModal } from './DocumentoIAModal'
import { DescompuestoObraModal, DescripcionObraModal } from './PartidaObraModales'
import type { ColumnaRejilla, ItemMenuContextual } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import { useDiccionario } from '../lib/useDiccionario'
import { useToast } from '../toast'
import { useWorkspace } from '../workspace'

export interface FilaObra {
  id: string
  tipo: 'capitulo' | 'partida'
  nivel: number
  codigo: string
  resumen: string
  /** Descripción ampliada, propia de la obra (se copia del origen al vincular
   *  y desde ahí va por su cuenta). */
  texto: string | null
  unidad: string
  medicion: string
  precio: string
  importe: string
  precioVenta: string
  importeVenta: string
  /** Capítulo contenedor (de la partida) o padre (del capítulo). */
  padreId: string | null
  orden: number
  tieneDesglose: boolean
  esAnexo: boolean
  /** Código del presupuesto del que salió, o null si se creó en obra. */
  origen: string | null
  partida?: PartidaObra
}

const RETARDO_GUARDADO = 700

function aplanar(nodos: NodoObra[], nivel = 0, padreId: string | null = null): FilaObra[] {
  const filas: FilaObra[] = []
  for (const nodo of nodos) {
    filas.push({
      id: nodo.id,
      tipo: 'capitulo',
      nivel,
      codigo: nodo.codigo,
      resumen: nodo.resumen,
      texto: nodo.texto,
      unidad: '',
      medicion: '',
      precio: '',
      importe: nodo.importe,
      precioVenta: '',
      importeVenta: nodo.importe_venta,
      padreId,
      orden: nodo.orden,
      tieneDesglose: false,
      esAnexo: nodo.es_anexo,
      origen: nodo.origen_codigo,
    })
    for (const partida of nodo.partidas) {
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
        precioVenta: partida.precio_venta,
        importeVenta: partida.importe_venta,
        padreId: nodo.id,
        orden: partida.orden,
        tieneDesglose: partida.tiene_desglose,
        esAnexo: partida.es_anexo,
        origen: partida.origen_codigo,
        partida,
      })
    }
    filas.push(...aplanar(nodo.hijos, nivel + 1, nodo.id))
  }
  return filas
}

type Campo = 'codigo' | 'resumen' | 'unidad' | 'medicion' | 'precio' | 'precio_venta'

export function RejillaObra({
  obraId,
  arbol,
  onCambio,
  onMedir,
  onSeleccionar,
  seleccionadaId,
}: {
  obraId: string
  arbol: ArbolObra
  onCambio: () => void
  onMedir: (partida: PartidaObra) => void
  onSeleccionar?: (fila: FilaObra | null) => void
  seleccionadaId?: string | null
}) {
  const { notificar } = useToast()
  const { modules } = useWorkspace()
  const iaActiva = modules.some((m) => m.code === 'ia' && m.is_active)
  const unidadesMedida = useDiccionario('unidad_medida')
  const filasDelServidor = useMemo(() => aplanar(arbol.capitulos), [arbol])
  const [filas, setFilas] = useState<FilaObra[]>(filasDelServidor)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [replegados, setReplegados] = useState<Set<string>>(new Set())
  const [filtros, setFiltros] = useState<Record<string, string>>({})
  const [marcadas, setMarcadas] = useState<string[]>([])
  const [verDescompuestoDe, setVerDescompuestoDe] = useState<FilaObra | null>(null)
  const [descripcionDe, setDescripcionDe] = useState<FilaObra | null>(null)
  // "Arrastrar a la obra": mismo patrón que en presupuestos
  // (`RejillaPresupuesto.documentoIA`) — `partidaId` cuando el fichero se
  // soltó/pidió sobre una partida ya existente, para que la IA pueda
  // proponerle mediciones directamente en vez de solo crear un capítulo.
  const [documentoIA, setDocumentoIA] = useState<{
    ficheros: File[]
    partidaId: string | null
  } | null>(null)
  const inputFicheroRef = useRef<HTMLInputElement>(null)
  const filaParaSubir = useRef<FilaObra | null>(null)

  // Cola de cambios pendientes: `${tipo}:${id}:${campo}` → valor. La clave
  // incluye el campo para que editar «precio» no reenvíe la «medición» que ya
  // se había guardado y la pise con un valor viejo.
  const cambios = useRef<Map<string, { fila: FilaObra; campo: Campo; valor: string }>>(new Map())
  const temporizador = useRef<number | undefined>(undefined)
  const filaActiva = useRef<FilaObra | null>(null)

  const porId = useMemo(() => new Map(filas.map((f) => [f.id, f])), [filas])
  const conHijos = useMemo(
    () => new Set(filas.map((f) => f.padreId).filter((x): x is string => Boolean(x))),
    [filas],
  )

  // Solo se pisa el estado local si no hay nada a medio escribir: si no, una
  // recarga del padre borraría lo que el usuario acaba de teclear.
  useEffect(() => {
    if (cambios.current.size === 0) setFilas(filasDelServidor)
  }, [filasDelServidor])

  const ocultaPorAncestro = useCallback(
    (fila: FilaObra) => {
      let padre = fila.padreId
      while (padre) {
        if (replegados.has(padre)) return true
        padre = porId.get(padre)?.padreId ?? null
      }
      return false
    },
    [replegados, porId],
  )

  const filtrando = Object.values(filtros).some((v) => v.trim() !== '')
  const idsCoincidentes = useMemo(() => {
    if (!filtrando) return null
    const activos = Object.entries(filtros).filter(([, v]) => v.trim() !== '')
    const crudo = (f: FilaObra, columnaId: string) => {
      switch (columnaId) {
        case 'codigo':
          return f.codigo
        case 'resumen':
          return f.resumen
        case 'origen':
          return f.origen ?? ''
        case 'unidad':
          return f.unidad
        case 'medicion':
          return f.medicion
        case 'precio':
          return f.precio
        case 'importe':
          return f.importe
        default:
          return ''
      }
    }
    const encajan = filas.filter((f) =>
      activos.every(([col, valor]) =>
        crudo(f, col).toLowerCase().includes(valor.trim().toLowerCase()),
      ),
    )
    // Se acompañan de sus ancestros (si no, la fila aparece desgajada) y, si es
    // un capítulo, de todo lo que cuelga.
    const visibles = new Set<string>()
    for (const fila of encajan) {
      visibles.add(fila.id)
      let padre = fila.padreId
      while (padre) {
        visibles.add(padre)
        padre = porId.get(padre)?.padreId ?? null
      }
      if (fila.tipo === 'capitulo') {
        const pendientes = [fila.id]
        while (pendientes.length) {
          const actual = pendientes.pop()!
          for (const hija of filas.filter((f) => f.padreId === actual)) {
            visibles.add(hija.id)
            pendientes.push(hija.id)
          }
        }
      }
    }
    return visibles
  }, [filtrando, filtros, filas, porId])

  const filasVisibles = filtrando
    ? filas.filter((f) => idsCoincidentes?.has(f.id) ?? false)
    : filas.filter((f) => !ocultaPorAncestro(f))

  const volcar = useCallback(async () => {
    const tanda = [...cambios.current.values()]
    if (tanda.length === 0) return
    cambios.current.clear()
    setGuardando(true)
    try {
      for (const { fila, campo, valor } of tanda) {
        if (fila.tipo === 'capitulo') {
          if (campo === 'codigo' || campo === 'resumen') {
            await api.obraCapitulos.update(fila.id, { [campo]: valor })
          }
          continue
        }
        await api.obraPartidas.update(fila.id, { [campo]: valor })
      }
      setError(null)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }, [onCambio])

  // Al desmontar se vuelca lo pendiente: cambiar de pestaña con una edición a
  // medio guardar no debe perderla.
  useEffect(() => {
    return () => {
      void volcar()
    }
  }, [volcar])

  function encolar(fila: FilaObra, campo: Campo, valor: string) {
    cambios.current.set(`${fila.tipo}:${fila.id}:${campo}`, { fila, campo, valor })
    window.clearTimeout(temporizador.current)
    temporizador.current = window.setTimeout(() => void volcar(), RETARDO_GUARDADO)
  }

  function editarLocal(id: string, cambio: Partial<FilaObra>) {
    setFilas((actuales) => actuales.map((f) => (f.id === id ? { ...f, ...cambio } : f)))
  }

  function alEditar(fila: FilaObra, columnaId: string, valor: string) {
    switch (columnaId) {
      case 'codigo':
        editarLocal(fila.id, { codigo: valor })
        return encolar(fila, 'codigo', valor)
      case 'resumen':
        editarLocal(fila.id, { resumen: valor })
        return encolar(fila, 'resumen', valor)
      case 'unidad':
        editarLocal(fila.id, { unidad: valor })
        return encolar(fila, 'unidad', valor)
      case 'medicion':
        editarLocal(fila.id, { medicion: valor })
        return encolar(fila, 'medicion', valor)
      case 'precio':
        editarLocal(fila.id, { precio: valor })
        return encolar(fila, 'precio', valor)
      case 'precio_venta':
        editarLocal(fila.id, { precioVenta: valor })
        return encolar(fila, 'precio_venta', valor)
    }
  }

  async function guardarDescripcion(fila: FilaObra, html: string) {
    if (fila.tipo === 'capitulo') await api.obraCapitulos.update(fila.id, { texto: html })
    else await api.obraPartidas.update(fila.id, { texto: html })
    editarLocal(fila.id, { texto: html })
    onCambio()
  }

  /** PDF/imagen/Excel arrastrados a una fila del árbol — la obra no importa
   *  BC3 (no tiene descompuesto que rellenar con uno), así que aquí todo lo
   *  admitido va derecho al chat con la IA, a diferencia de `manejarFicheros`
   *  en `RejillaPresupuesto`. */
  function manejarFicheros(fila: FilaObra, archivos: File[]) {
    const docs: File[] = []
    const rechazados: string[] = []
    for (const archivo of archivos) {
      const nombre = archivo.name.toLowerCase()
      const esPdf = archivo.type === 'application/pdf' || nombre.endsWith('.pdf')
      const esImagen = archivo.type.startsWith('image/')
      const esExcel = nombre.endsWith('.xlsx')
      if (esPdf || esImagen || esExcel) docs.push(archivo)
      else rechazados.push(archivo.name)
    }
    if (docs.length > 0) {
      setDocumentoIA({ ficheros: docs, partidaId: fila.tipo === 'partida' ? fila.id : null })
    }
    if (rechazados.length > 0) {
      notificar(`No se puede soltar aquí: ${rechazados.join(', ')} (solo PDF, imagen o Excel)`)
    }
  }

  function pedirFichero(fila: FilaObra) {
    filaParaSubir.current = fila
    inputFicheroRef.current?.click()
  }

  function contenedorDe(fila: FilaObra | null): string | null {
    if (!fila) return null
    return fila.tipo === 'capitulo' ? fila.id : fila.padreId
  }

  async function nuevoCapitulo(actual: FilaObra | null) {
    try {
      await api.obras.addCapitulo(obraId, {
        resumen: 'Nuevo capítulo',
        parent_id: actual ? contenedorDe(actual) : null,
      })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function nuevaPartida(actual: FilaObra | null) {
    const capituloId = contenedorDe(actual)
    if (!capituloId) {
      setError('Elige antes un capítulo: una partida siempre cuelga de uno.')
      return
    }
    try {
      await api.obraCapitulos.addPartida(capituloId, { resumen: 'Nueva partida' })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminarFila(fila: FilaObra) {
    const que =
      fila.tipo === 'capitulo'
        ? `el capítulo «${fila.resumen}» y todo su contenido`
        : `la partida «${fila.resumen}» y sus mediciones`
    if (!window.confirm(`¿Eliminar ${que} del árbol de la obra?`)) return
    try {
      if (fila.tipo === 'capitulo') await api.obraCapitulos.remove(fila.id)
      else await api.obraPartidas.remove(fila.id)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function indentar(fila: FilaObra, direccion: 1 | -1) {
    // Mismo comportamiento que en presupuestos (Alt+→ / Alt+←), para que el
    // gesto no signifique dos cosas distintas según la pantalla.
    setError(null)
    const indice = filas.findIndex((f) => f.id === fila.id)
    try {
      if (direccion === 1) {
        // Colgar del capítulo anterior que pueda contenerlo. Si resultara ser
        // un descendiente suyo, el servidor lo rechaza: cerrar un ciclo
        // dejaría la rama fuera del árbol y sin forma de volver a verla.
        const anterior = [...filas.slice(0, indice)]
          .reverse()
          .find((f) => f.tipo === 'capitulo' && f.id !== fila.id)
        if (!anterior) return
        if (fila.tipo === 'partida') {
          await api.obraPartidas.update(fila.id, { capitulo_id: anterior.id })
        } else {
          await api.obraCapitulos.update(fila.id, { parent_id: anterior.id })
        }
      } else {
        // Subir un nivel: pasar a colgar del abuelo.
        const padre = fila.padreId ? porId.get(fila.padreId) : null
        if (!padre) return
        if (fila.tipo === 'partida') {
          // Una partida siempre cuelga de un capítulo: sin abuelo, no hay
          // adónde subirla.
          if (!padre.padreId) return
          await api.obraPartidas.update(fila.id, { capitulo_id: padre.padreId })
        } else {
          await api.obraCapitulos.update(fila.id, { parent_id: padre.padreId })
        }
      }
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function mover(fila: FilaObra, destino: FilaObra) {
    const capituloId = contenedorDe(destino)
    if (!capituloId || capituloId === fila.padreId) return
    try {
      if (fila.tipo === 'partida') await api.obraPartidas.update(fila.id, { capitulo_id: capituloId })
      else await api.obraCapitulos.update(fila.id, { parent_id: capituloId })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const columnas: ColumnaRejilla<FilaObra>[] = [
    {
      id: 'codigo',
      etiqueta: 'Código',
      ancho: '170px',
      sangrada: true,
      valor: (f) => f.codigo,
      editable: () => true,
      prefijo: (f) =>
        f.tipo === 'capitulo' && conHijos.has(f.id) ? (
          <button
            className="rejilla__plegar"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation()
              setReplegados((actuales) => {
                const siguiente = new Set(actuales)
                if (siguiente.has(f.id)) siguiente.delete(f.id)
                else siguiente.add(f.id)
                return siguiente
              })
            }}
            aria-label={replegados.has(f.id) ? 'Desplegar' : 'Replegar'}
          >
            {replegados.has(f.id) ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          </button>
        ) : null,
    },
    {
      id: 'resumen',
      etiqueta: 'Descripción',
      ancho: '280px',
      valor: (f) => f.resumen,
      editable: () => true,
      prefijo: (f) =>
        f.esAnexo || f.tieneDesglose ? (
          <span className="rejilla__avisos">
            {f.esAnexo && (
              <Tooltip texto="Entró después de arrancar la obra: anexo o adenda">
                <span className="rejilla__aviso arbol-obra__anexo">
                  <GitBranch size={12} aria-hidden="true" />
                </span>
              </Tooltip>
            )}
            {f.tieneDesglose && (
              <Tooltip texto="La medición sale de sus parciales">
                <span className="rejilla__aviso">
                  <Ruler size={12} aria-hidden="true" />
                </span>
              </Tooltip>
            )}
          </span>
        ) : null,
    },
    {
      id: 'origen',
      etiqueta: 'Procede de',
      ancho: '120px',
      valor: (f) => f.origen ?? (f.esAnexo ? 'En obra' : ''),
    },
    {
      id: 'unidad',
      etiqueta: 'Ud.',
      ancho: '90px',
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
      // Con parciales la medición es su suma: teclearla a mano la perdería en
      // el siguiente recálculo.
      editable: (f) => f.tipo === 'partida' && !f.tieneDesglose,
    },
    {
      id: 'precio',
      etiqueta: 'Coste',
      ancho: '105px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'partida' ? formatoImporte(f.precio) : ''),
      editable: (f) => f.tipo === 'partida',
    },
    {
      id: 'importe',
      etiqueta: 'Importe coste',
      ancho: '125px',
      tipo: 'numero',
      valor: (f) => formatoImporte(f.importe),
      total: `${formatoImporte(arbol.totales.coste)} €`,
    },
    {
      id: 'precio_venta',
      etiqueta: 'Venta',
      ancho: '105px',
      tipo: 'numero',
      valor: (f) => (f.tipo === 'partida' ? formatoImporte(f.precioVenta) : ''),
      editable: (f) => f.tipo === 'partida',
    },
    {
      id: 'importe_venta',
      etiqueta: 'Importe venta',
      ancho: '125px',
      tipo: 'numero',
      valor: (f) => formatoImporte(f.importeVenta),
      total: `${formatoImporte(arbol.totales.venta)} €`,
    },
  ]

  function menuContextualDe(fila: FilaObra): ItemMenuContextual[] {
    const items: ItemMenuContextual[] = [
      {
        id: 'nueva-partida',
        etiqueta: 'Añadir partida aquí',
        icono: <Plus size={14} aria-hidden="true" />,
        onClick: () => void nuevaPartida(fila),
      },
      {
        id: 'nuevo-capitulo',
        etiqueta: 'Añadir capítulo dentro',
        icono: <FolderPlus size={14} aria-hidden="true" />,
        onClick: () => void nuevoCapitulo(fila),
      },
    ]
    if (fila.tipo === 'partida' && fila.partida) {
      items.push({
        id: 'medir',
        etiqueta: 'Medir en obra',
        icono: <Ruler size={14} aria-hidden="true" />,
        onClick: () => onMedir(fila.partida!),
      })
    }
    if (fila.tipo === 'partida' && fila.partida?.origen_partida_id) {
      items.push({
        id: 'descompuesto',
        etiqueta: 'Ver descompuesto',
        icono: <Boxes size={14} aria-hidden="true" />,
        onClick: () => setVerDescompuestoDe(fila),
      })
    }
    items.push({
      id: 'descripcion',
      etiqueta: 'Descripción ampliada',
      icono: <AlignLeft size={14} aria-hidden="true" />,
      onClick: () => setDescripcionDe(fila),
    })
    if (fila.origen && fila.partida?.origen_partida_id) {
      items.push({
        id: 'ver-origen',
        etiqueta: `Ver en ${fila.origen}`,
        onClick: () =>
          window.open(`/presupuestos/${fila.partida!.origen_presupuesto_id}`, '_blank'),
      })
    }
    if (iaActiva) {
      items.push({
        id: 'preguntar-ia',
        etiqueta: 'Preguntar a la IA…',
        icono: <Sparkles size={14} aria-hidden="true" />,
        onClick: () =>
          setDocumentoIA({ ficheros: [], partidaId: fila.tipo === 'partida' ? fila.id : null }),
      })
      items.push({
        id: 'subir-fichero',
        etiqueta: 'Subir documento (PDF, imagen o Excel)…',
        icono: <Upload size={14} aria-hidden="true" />,
        onClick: () => pedirFichero(fila),
      })
    }
    items.push({
      id: 'eliminar',
      etiqueta: 'Eliminar',
      icono: <Trash2 size={14} aria-hidden="true" />,
      peligroso: true,
      onClick: () => void eliminarFila(fila),
    })
    return items
  }

  return (
    <>
      <div className="rejilla-barra">
        {conHijos.size > 0 && (
          <>
            <Tooltip texto="Replegar todos los capítulos">
              <button className="btn btn--sm" onClick={() => setReplegados(new Set(conHijos))}>
                <ChevronsDownUp size={14} aria-hidden="true" />
              </button>
            </Tooltip>
            <Tooltip texto="Desplegar todo">
              <button className="btn btn--sm" onClick={() => setReplegados(new Set())}>
                <ChevronsUpDown size={14} aria-hidden="true" />
              </button>
            </Tooltip>
          </>
        )}
        <span className="rejilla-barra__estado">
          {guardando ? 'Guardando…' : cambios.current.size > 0 ? 'Sin guardar…' : ''}
        </span>
        <button className="btn btn--sm" onClick={() => void nuevoCapitulo(null)}>
          <FolderPlus size={14} aria-hidden="true" />
          Capítulo
        </button>
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={filasVisibles}
        columnas={columnas}
        idDe={(f) => f.id}
        nivelDe={(f) => f.nivel}
        claseDe={(f) =>
          [f.tipo === 'capitulo' ? 'fila-capitulo' : '', f.esAnexo ? 'fila-anexo' : '']
            .filter(Boolean)
            .join(' ') || undefined
        }
        onEditar={(f, col, valor) => alEditar(f, col, valor)}
        onNuevaFila={(actual) => void nuevaPartida(actual ?? filaActiva.current)}
        onEliminarFila={(f) => void eliminarFila(f)}
        onIndentar={(f, d) => void indentar(f, d)}
        onSeleccionar={(f) => {
          filaActiva.current = f
          onSeleccionar?.(f)
        }}
        seleccionadaId={seleccionadaId}
        onMarcarVarias={setMarcadas}
        // `onCopiar` es lo que habilita el arrastre en `RejillaEditable`; aquí
        // no hay portapapeles entre obras, solo mover dentro del árbol.
        onCopiar={setMarcadas}
        onSoltarEn={(destino) => {
          const origen = marcadas.length === 1 ? porId.get(marcadas[0]) : null
          if (origen && destino && origen.id !== destino.id) void mover(origen, destino)
        }}
        onSoltarFichero={iaActiva ? manejarFicheros : undefined}
        menuContextual={menuContextualDe}
        filtros={filtros}
        onFiltrar={(columnaId, valor) => setFiltros((f) => ({ ...f, [columnaId]: valor }))}
        vacia={
          <EmptyState title="La obra no tiene partidas todavía">
            Trae las partidas de sus presupuestos, o crea un capítulo para empezar de cero.
          </EmptyState>
        }
        acciones={(f) => (
          <>
            {f.tipo === 'partida' && f.partida && (
              <Tooltip texto="Medir en obra">
                <button className="btn btn--sm" onClick={() => onMedir(f.partida!)}>
                  <Ruler size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            )}
            {f.tipo === 'capitulo' && (
              <Tooltip texto="Añadir partida en este capítulo">
                <button className="btn btn--sm" onClick={() => void nuevaPartida(f)}>
                  <Plus size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            )}
            <Tooltip texto="Eliminar">
              <button className="btn btn--sm" onClick={() => void eliminarFila(f)}>
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </Tooltip>
          </>
        )}
      />

      {/* Alternativa sin arrastrar a "Subir documento" del menú contextual —
          oculto, lo dispara `pedirFichero` con `.click()`. */}
      <input
        ref={inputFicheroRef}
        type="file"
        multiple
        accept=".xlsx,application/pdf,image/png,image/jpeg,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => {
          const archivos = Array.from(e.target.files ?? [])
          e.target.value = ''
          if (archivos.length > 0 && filaParaSubir.current) {
            manejarFicheros(filaParaSubir.current, archivos)
          }
        }}
      />

      {documentoIA && (
        <DocumentoIAModal
          ficheros={documentoIA.ficheros}
          entidad="obra"
          entidadId={obraId}
          conversar={(ficheros, mensajes) =>
            api.obras.documentoConversarIA(
              obraId,
              ficheros,
              mensajes,
              documentoIA.partidaId ?? undefined,
            )
          }
          aplicarPropuesta={async (propuesta) => {
            if (propuesta.tipo === 'anadir_mediciones_partida') {
              if (!propuesta.partida_id) throw new Error('La propuesta no trae la partida de destino')
              const creadas = await api.obras.aplicarMedicionesIA({
                partida_id: propuesta.partida_id,
                lineas: propuesta.mediciones_propuestas.map(
                  ({ comentario, uds, longitud, anchura, altura }) => ({
                    comentario,
                    uds,
                    longitud,
                    anchura,
                    altura,
                  }),
                ),
              })
              return `Hecho: ${creadas.length} línea${creadas.length === 1 ? '' : 's'} de medición añadida${creadas.length === 1 ? '' : 's'} a la partida.`
            }
            const resultado = await api.obras.aplicarPropuestaIA(obraId, {
              capitulo_resumen: propuesta.capitulo_resumen || 'Importado de documento',
              partidas: propuesta.partidas_propuestas,
            })
            return `Hecho: capítulo «${resultado.resumen}» creado con ${resultado.partidas} partida${resultado.partidas === 1 ? '' : 's'}.`
          }}
          onClose={() => setDocumentoIA(null)}
          onCambio={onCambio}
        />
      )}

      {verDescompuestoDe?.partida?.origen_partida_id && (
        <DescompuestoObraModal
          origenPartidaId={verDescompuestoDe.partida.origen_partida_id}
          origenCodigo={verDescompuestoDe.origen}
          titulo={verDescompuestoDe.resumen}
          onClose={() => setVerDescompuestoDe(null)}
        />
      )}

      {descripcionDe && (
        <DescripcionObraModal
          id={descripcionDe.id}
          obraId={obraId}
          titulo={descripcionDe.resumen}
          html={descripcionDe.texto}
          onGuardar={(html) => guardarDescripcion(descripcionDe, html)}
          onClose={() => setDescripcionDe(null)}
        />
      )}
    </>
  )
}
