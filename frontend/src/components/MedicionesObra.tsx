/** Los parciales de una partida de obra: lo que se ha medido de verdad.
 *
 *  Hermana de `MedicionesPartida` (la de presupuestos) sin fórmulas: la
 *  fórmula es una herramienta de la fase de presupuestar, y en obra se mide lo
 *  que hay. El cálculo del parcial es el mismo (`parcial_de` en el backend):
 *  las dimensiones que no se rellenan valen 1, no 0.
 *
 *  Editar aquí NO toca el presupuesto firmado con el cliente: son tablas
 *  distintas, y eso es justamente el motivo de que la obra tenga árbol propio.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { api } from '../lib/api'
import type { MedicionObra, PartidaObra, PartidaObraDetalle } from '../lib/api'
import type { ColumnaRejilla } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'

const RETARDO_GUARDADO = 700

type Campo = 'comentario' | 'uds' | 'longitud' | 'anchura' | 'altura'

export function MedicionesObra({
  partida,
  onCambio,
}: {
  partida: PartidaObra
  /** El árbol tiene que recargarse: la medición de la partida es su suma. */
  onCambio: () => void
}) {
  const [detalle, setDetalle] = useState<PartidaObraDetalle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [filtros, setFiltros] = useState<Record<string, string>>({})

  // Clave por campo, no por fila: encolar la fila entera hacía que una edición
  // pisara con un valor viejo la que acababa de guardarse.
  const cambios = useRef<Map<string, { id: string; campo: Campo; valor: string | null }>>(new Map())
  const temporizador = useRef<number | undefined>(undefined)

  const cargar = useCallback(async () => {
    try {
      setDetalle(await api.obraPartidas.get(partida.id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [partida.id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const volcar = useCallback(async () => {
    const tanda = [...cambios.current.values()]
    if (tanda.length === 0) return
    cambios.current.clear()
    setGuardando(true)
    try {
      for (const { id, campo, valor } of tanda) {
        await api.obraMediciones.update(id, { [campo]: valor })
      }
      await cargar()
      onCambio()
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }, [cargar, onCambio])

  // Al desmontar se vuelca lo pendiente: cerrar el widget con una edición a
  // medio guardar no debe perderla.
  useEffect(() => {
    return () => {
      void volcar()
    }
  }, [volcar])

  function encolar(linea: MedicionObra, campo: Campo, valor: string) {
    const limpio = valor.trim()
    cambios.current.set(`${linea.id}:${campo}`, {
      id: linea.id,
      campo,
      // Un hueco no es un cero: vaciar una dimensión la devuelve a «no
      // informada», que cuenta como 1 en el parcial.
      valor: limpio === '' ? null : limpio,
    })
    setDetalle((actual) =>
      actual === null
        ? actual
        : {
            ...actual,
            lineas: actual.lineas.map((l) =>
              l.id === linea.id ? { ...l, [campo]: limpio === '' ? null : limpio } : l,
            ),
          },
    )
    window.clearTimeout(temporizador.current)
    temporizador.current = window.setTimeout(() => void volcar(), RETARDO_GUARDADO)
  }

  async function anadir() {
    try {
      await api.obraPartidas.addMedicion(partida.id, { comentario: null, uds: '1' })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar(linea: MedicionObra) {
    try {
      await api.obraMediciones.remove(linea.id)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const lineas = detalle?.lineas ?? []
  const filtrando = Object.values(filtros).some((v) => v.trim() !== '')
  const visibles = filtrando
    ? lineas.filter((l) =>
        Object.entries(filtros).every(([col, valor]) => {
          if (valor.trim() === '') return true
          const crudo = col === 'comentario' ? (l.comentario ?? '') : String((l as never)[col] ?? '')
          return crudo.toLowerCase().includes(valor.trim().toLowerCase())
        }),
      )
    : lineas

  const total = lineas.reduce((suma, l) => suma + Number(l.parcial), 0)

  const columnas: ColumnaRejilla<MedicionObra>[] = [
    {
      id: 'comentario',
      etiqueta: 'Descripción',
      ancho: '220px',
      valor: (l) => l.comentario ?? '',
      editable: () => true,
    },
    {
      id: 'uds',
      etiqueta: 'Uds.',
      ancho: '90px',
      tipo: 'numero',
      valor: (l) => l.uds ?? '',
      editable: () => true,
    },
    {
      id: 'longitud',
      etiqueta: 'Longitud',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => l.longitud ?? '',
      editable: () => true,
    },
    {
      id: 'anchura',
      etiqueta: 'Anchura',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => l.anchura ?? '',
      editable: () => true,
    },
    {
      id: 'altura',
      etiqueta: 'Altura',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => l.altura ?? '',
      editable: () => true,
    },
    {
      id: 'parcial',
      etiqueta: 'Parcial',
      ancho: '110px',
      tipo: 'numero',
      valor: (l) => formatoImporte(l.parcial, 3),
      total: formatoImporte(String(total), 3),
    },
  ]

  return (
    <>
      <div className="rejilla-barra">
        <span className="rejilla-barra__titulo">
          {partida.codigo && <span className="muted">{partida.codigo} </span>}
          {partida.resumen}
        </span>
        <span className="rejilla-barra__estado">{guardando ? 'Guardando…' : ''}</span>
        <button className="btn btn--sm" onClick={() => void anadir()}>
          <Plus size={14} aria-hidden="true" />
          Parcial
        </button>
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={visibles}
        columnas={columnas}
        idDe={(l) => l.id}
        onEditar={(l, col, valor) => encolar(l, col as Campo, valor)}
        onNuevaFila={() => void anadir()}
        onEliminarFila={(l) => void eliminar(l)}
        filtros={filtros}
        onFiltrar={(columnaId, valor) => setFiltros((f) => ({ ...f, [columnaId]: valor }))}
        vacia={
          <EmptyState title="Sin parciales">
            Añade parciales para medir lo ejecutado. Mientras no haya ninguno, la medición es la
            que se teclea en el árbol.
          </EmptyState>
        }
        acciones={(l) => (
          <Tooltip texto="Eliminar este parcial">
            <button className="btn btn--sm" onClick={() => void eliminar(l)}>
              <Trash2 size={14} aria-hidden="true" />
            </button>
          </Tooltip>
        )}
      />
    </>
  )
}
