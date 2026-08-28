/** Mediciones de una partida de Pedido/Factura/FacturaRecibida (Fase 3;
 *  copiar/pegar entre partidas de la misma entidad añadido en la Fase 5).
 *
 *  Versión mínima de `MedicionesPartida.tsx`: tabla simple de
 *  uds/longitud/anchura/altura sin fórmulas (fuera de alcance — ver la nota
 *  de alcance de la Fase 3 en el plan). Parametrizada por props inyectadas,
 *  mismo criterio que `RejillaDocumento`. */

import { useEffect, useRef, useState } from 'react'
import { Clipboard, Plus, Trash2 } from 'lucide-react'

import { BotonAtajos } from './AtajosTeclado'
import { PegarModal } from './PegarModal'
import type { ColumnaRejilla } from './RejillaEditable'
import { RejillaEditable } from './RejillaEditable'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import type { AlcancePegado, MedicionDocumento, ResultadoPegado } from '../lib/api'
import type { OrigenEntidadPortapapeles } from '../lib/portapapeles'
import { copiarAlPortapapeles, leerPortapapeles } from '../lib/portapapeles'
import { useToast } from '../toast'

const RETARDO_GUARDADO = 700

type Campo = 'comentario' | 'uds' | 'longitud' | 'anchura' | 'altura'

export function MedicionesDocumento({
  mediciones,
  unidad,
  medicionTotal,
  precio,
  importe,
  onCrear,
  onActualizar,
  onEliminar,
  onCambio,
  origenEntidad,
  origenEtiqueta,
  onPegar: pegarMediciones,
}: {
  mediciones: MedicionDocumento[]
  unidad: string
  medicionTotal: string
  precio: string
  importe: string
  onCrear: () => Promise<unknown>
  onActualizar: (
    id: string,
    campos: Partial<{
      comentario: string | null
      uds: string | null
      longitud: string | null
      anchura: string | null
      altura: string | null
    }>,
  ) => Promise<unknown>
  onEliminar: (id: string) => Promise<unknown>
  onCambio: () => void
  /** Qué entidad es este documento (Fase 5): una línea copiada de otro
   *  Pedido/Factura solo se ofrece pegar si viene de la MISMA entidad. */
  origenEntidad: OrigenEntidadPortapapeles
  /** "PED-24 · Solera de hormigón" — para el mensaje al copiar/pegar. */
  origenEtiqueta: string
  onPegar: (datos: { medicion_ids: string[]; alcance: AlcancePegado }) => Promise<ResultadoPegado>
}) {
  const { notificar } = useToast()
  const [filas, setFilas] = useState<MedicionDocumento[]>(mediciones)
  const [error, setError] = useState<string | null>(null)
  const [pendiente, setPendiente] = useState(false)
  const [pegando, setPegando] = useState<{ ids: string[]; origenEtiqueta: string } | null>(null)
  const cambios = useRef<Map<string, Record<string, string | null>>>(new Map())
  const temporizador = useRef<number | undefined>(undefined)

  // Sin nada a medio teclear, una recarga del padre (tras crear/borrar una
  // línea, o al llegar aquí `onCambio`) reemplaza el estado local sin más.
  // El padre monta este componente con `key={partidaId}` al cambiar de
  // partida seleccionada, así que un cambio de partida siempre remonta en
  // limpio en vez de arrastrar ediciones a medio guardar de la anterior.
  useEffect(() => {
    if (cambios.current.size === 0) setFilas(mediciones)
  }, [mediciones])

  function volcar() {
    const tanda = [...cambios.current.entries()]
    if (tanda.length === 0) return
    cambios.current.clear()
    setPendiente(false)
    void (async () => {
      try {
        for (const [id, campos] of tanda) await onActualizar(id, campos)
        setError(null)
        onCambio()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido')
      }
    })()
  }

  function encolar(linea: MedicionDocumento, campo: Campo, valor: string | null) {
    const previo = cambios.current.get(linea.id) ?? {}
    cambios.current.set(linea.id, { ...previo, [campo]: valor })
    setPendiente(true)
    window.clearTimeout(temporizador.current)
    temporizador.current = window.setTimeout(volcar, RETARDO_GUARDADO)
  }

  function editarLocal(id: string, cambio: Partial<MedicionDocumento>) {
    setFilas((actuales) => actuales.map((l) => (l.id === id ? { ...l, ...cambio } : l)))
  }

  async function anadir() {
    setError(null)
    try {
      await onCrear()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar(linea: MedicionDocumento) {
    try {
      await onEliminar(linea.id)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  function copiarLineas(ids: string[]) {
    if (ids.length === 0) return
    copiarAlPortapapeles({ tipo: 'lineas_medicion', origenEntidad, ids, origenEtiqueta })
    notificar(ids.length === 1 ? 'Línea copiada' : `${ids.length} líneas copiadas`)
  }

  function pegar() {
    const contenido = leerPortapapeles()
    if (!contenido) {
      notificar('No hay nada copiado')
      return
    }
    if (contenido.origenEntidad !== origenEntidad) {
      notificar('Lo copiado es de otro tipo de documento y no se puede pegar aquí')
      return
    }
    if (contenido.tipo !== 'lineas_medicion') {
      notificar('Lo copiado no se puede pegar aquí')
      return
    }
    setPegando({ ids: contenido.ids, origenEtiqueta: contenido.origenEtiqueta })
  }

  async function confirmarPegado(alcance: AlcancePegado) {
    if (!pegando) return
    try {
      const resultado = await pegarMediciones({ medicion_ids: pegando.ids, alcance })
      setPegando(null)
      onCambio()
      notificar(resultado.pegadas === 1 ? 'Línea pegada' : `${resultado.pegadas} líneas pegadas`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setPegando(null)
    }
  }

  const columnas: ColumnaRejilla<MedicionDocumento>[] = [
    {
      id: 'comentario',
      etiqueta: 'Comentario',
      ancho: '220px',
      valor: (l) => l.comentario ?? '',
      editable: () => true,
    },
    {
      id: 'uds',
      etiqueta: 'Uds',
      ancho: '90px',
      tipo: 'numero',
      valor: (l) => (l.uds ? formatoImporte(l.uds, 3) : ''),
      editable: () => true,
    },
    {
      id: 'longitud',
      etiqueta: 'Longitud',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => (l.longitud ? formatoImporte(l.longitud, 3) : ''),
      editable: () => true,
    },
    {
      id: 'anchura',
      etiqueta: 'Anchura',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => (l.anchura ? formatoImporte(l.anchura, 3) : ''),
      editable: () => true,
    },
    {
      id: 'altura',
      etiqueta: 'Altura',
      ancho: '100px',
      tipo: 'numero',
      valor: (l) => (l.altura ? formatoImporte(l.altura, 3) : ''),
      editable: () => true,
    },
    {
      id: 'parcial',
      etiqueta: 'Parcial',
      ancho: '110px',
      tipo: 'numero',
      valor: (l) => formatoImporte(l.parcial, 3),
      total: `${formatoImporte(medicionTotal, 3)} ${unidad}`,
    },
  ]

  return (
    <>
      <div className="rejilla-barra">
        <BotonAtajos />
        <button className="btn btn--sm" onClick={() => void anadir()}>
          <Plus size={14} aria-hidden="true" />
          Línea
        </button>
        {(() => {
          const contenido = leerPortapapeles()
          if (!contenido || contenido.origenEntidad !== origenEntidad || contenido.tipo !== 'lineas_medicion')
            return null
          return (
            <Tooltip texto={`Pegar línea(s) de «${contenido.origenEtiqueta}»`}>
              <button className="btn btn--sm" onClick={pegar}>
                <Clipboard size={14} aria-hidden="true" />
                Pegar
              </button>
            </Tooltip>
          )
        })()}
        <span className="rejilla-barra__estado">
          {pendiente ? <span className="muted">Sin guardar…</span> : <span className="muted">Guardado</span>}
        </span>
      </div>

      <ErrorNotice error={error} />

      <RejillaEditable
        filas={filas}
        columnas={columnas}
        idDe={(l) => l.id}
        onEditar={(linea, columnaId, valor) => {
          if (columnaId === 'parcial') return
          const limpio = valor.trim() === '' ? null : valor.replace(',', '.')
          editarLocal(linea.id, { [columnaId]: limpio } as Partial<MedicionDocumento>)
          encolar(linea, columnaId as Campo, limpio)
        }}
        onNuevaFila={() => anadir()}
        onEliminarFila={(l) => void eliminar(l)}
        onCopiar={copiarLineas}
        onPegar={pegar}
        vacia={
          <EmptyState title="Sin líneas de medición">Añade una línea para desglosar la cantidad.</EmptyState>
        }
        acciones={(l) => (
          <button
            className="btn btn--sm btn--danger btn--solo-icono"
            aria-label="Eliminar esta línea"
            onClick={() => void eliminar(l)}
          >
            <Trash2 size={14} aria-hidden="true" />
          </button>
        )}
      />

      {pegando && (
        <PegarModal
          cantidad={pegando.ids.length}
          origenEtiqueta={pegando.origenEtiqueta}
          onElegir={(alcance) => void confirmarPegado(alcance)}
          onClose={() => setPegando(null)}
        />
      )}

      <div className="resumen-totales" style={{ marginTop: 'var(--sp-3)' }}>
        <div className="resumen-totales__fila is-total">
          <span>Medición total</span>
          <span className="resumen-totales__valor">
            {formatoImporte(medicionTotal, 3)} {unidad}
          </span>
        </div>
        <div className="resumen-totales__fila is-suave">
          <span>
            × {formatoImporte(precio)} €/{unidad}
          </span>
          <span className="resumen-totales__valor">{formatoImporte(importe)} €</span>
        </div>
      </div>
    </>
  )
}
