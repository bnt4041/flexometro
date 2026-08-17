import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FolderPlus, Layers, Plus, Ruler, Trash2 } from 'lucide-react'

import type { ColumnaRejilla, OpcionCelda } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { CambioLinea, NodoCapitulo, Partida, PresupuestoDetalle } from '../lib/api'
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
  tieneDesglose: boolean
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
      tieneDesglose: false,
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
        tieneDesglose: partida.tiene_desglose,
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
  const [filas, setFilas] = useState<FilaPresupuesto[]>(() => aplanar(presupuesto.capitulos))
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [pendiente, setPendiente] = useState(false)
  const cambios = useRef<Map<string, CambioLinea>>(new Map())
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)

  const filasDelServidor = useMemo(() => aplanar(presupuesto.capitulos), [presupuesto])

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

  function encolar(fila: FilaPresupuesto, campo: keyof CambioLinea, valor: string) {
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
      await api.capitulos.addPartida(capituloId, { resumen: '' })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function nuevoCapitulo(actual: FilaPresupuesto | null) {
    setError(null)
    try {
      const parentId = actual
        ? actual.tipo === 'capitulo'
          ? actual.padreId
          : actual.padreId
        : null
      await api.presupuestos.addCapitulo(presupuesto.id, {
        resumen: 'Nuevo capítulo',
        parent_id: parentId,
      })
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
      ancho: '150px',
      valor: (f) => f.codigo,
      editable: () => true,
      sangrada: true,
    },
    {
      id: 'resumen',
      etiqueta: 'Descripción',
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
    },
    {
      id: 'unidad',
      etiqueta: 'Ud.',
      ancho: '80px',
      valor: (f) => f.unidad,
      editable: (f) => f.tipo === 'partida',
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
      etiqueta: 'Importe',
      ancho: '120px',
      tipo: 'numero',
      valor: (f) => formatoImporte(f.importe),
    },
  ]

  return (
    <>
      <div className="rejilla-barra">
        <span className="rejilla-barra__ayuda muted">
          Enter edita y baja · Tab pasa de celda · Ctrl+Enter nueva partida · Alt+→/← sangra ·
          Ctrl+Supr borra
        </span>
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
        filas={filas}
        columnas={columnas}
        idDe={(f) => f.id}
        nivelDe={(f) => f.nivel}
        claseDe={(f) => (f.tipo === 'capitulo' ? 'fila-capitulo' : undefined)}
        onEditar={(f, col, valor, opcion) => void alEditar(f, col, valor, opcion)}
        onNuevaFila={(f) => void nuevaFila(f)}
        onEliminarFila={(f) => void eliminarFila(f)}
        onIndentar={(f, d) => void indentar(f, d)}
        onSeleccionar={onSeleccionar}
        seleccionadaId={seleccionadaId}
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
                      onClick={() => onIntegrarBanco(f.partida!)}
                    >
                      <Layers size={14} aria-hidden="true" />
                    </button>
                  </Tooltip>{' '}
                </>
              )}
              <Tooltip texto="Desglosar la medición">
                <button
                  className="btn btn--sm btn--solo-icono"
                  onClick={() => onMedir(f.partida!)}
                >
                  <Ruler size={14} aria-hidden="true" />
                </button>
              </Tooltip>{' '}
              <Tooltip texto="Eliminar esta partida">
                <button
                  className="btn btn--sm btn--danger btn--solo-icono"
                  onClick={() => void eliminarFila(f)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            </>
          ) : (
            <>
              <Tooltip texto="Añadir una partida en este capítulo">
                <button className="btn btn--sm btn--solo-icono" onClick={() => void nuevaFila(f)}>
                  <Plus size={14} aria-hidden="true" />
                </button>
              </Tooltip>{' '}
              <Tooltip texto="Eliminar este capítulo y su contenido">
                <button
                  className="btn btn--sm btn--danger btn--solo-icono"
                  onClick={() => void eliminarFila(f)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            </>
          )
        }
      />
    </>
  )
}
