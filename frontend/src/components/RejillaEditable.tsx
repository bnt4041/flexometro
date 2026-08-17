import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'

export interface OpcionCelda {
  valor: string
  etiqueta: string
  /** Texto secundario a la derecha (código, precio…). */
  detalle?: string
  /** Para "crear nuevo" y demás opciones que no salen de la búsqueda. */
  esAccion?: boolean
}

export interface ColumnaRejilla<F> {
  id: string
  etiqueta: string
  ancho?: string
  /** `texto` por defecto. `numero` alinea a la derecha y filtra la entrada. */
  tipo?: 'texto' | 'numero' | 'select' | 'autocompletado'
  valor: (fila: F) => string
  /** Sin esto, la celda es de solo lectura (se puede seleccionar, no editar). */
  editable?: (fila: F) => boolean
  /** Solo `select`. */
  opciones?: (fila: F) => OpcionCelda[]
  /** Solo `autocompletado`. */
  buscar?: (q: string, fila: F) => Promise<OpcionCelda[]>
  /** Sangra el contenido según el nivel de la fila (columna de código). */
  sangrada?: boolean
}

interface Props<F> {
  filas: F[]
  columnas: ColumnaRejilla<F>[]
  idDe: (fila: F) => string
  nivelDe?: (fila: F) => number
  claseDe?: (fila: F) => string | undefined
  /** Se llama al confirmar una celda. `opcion` viene relleno en select/autocompletado. */
  onEditar: (fila: F, columnaId: string, valor: string, opcion?: OpcionCelda) => void
  onNuevaFila?: (filaActual: F | null) => void
  onEliminarFila?: (fila: F) => void
  /** +1 indenta (Alt+→), -1 desindenta (Alt+←). */
  onIndentar?: (fila: F, direccion: 1 | -1) => void
  onSeleccionar?: (fila: F | null) => void
  seleccionadaId?: string | null
  acciones?: (fila: F) => ReactNode
  vacia?: ReactNode
}

const TECLAS_CONTROL = new Set([
  'Shift', 'Control', 'Alt', 'Meta', 'CapsLock', 'Escape', 'Tab', 'Enter',
  'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End',
  'PageUp', 'PageDown', 'Backspace', 'Delete', 'Insert',
])

/** Rejilla de edición por teclado al estilo de una hoja de cálculo (Fase 33).
 *
 *  Dos modos, como en Excel: en **navegación** las flechas mueven de celda; en
 *  **edición** (F2, Enter, o simplemente empezar a teclear) las flechas mueven
 *  el cursor dentro del texto. Enter confirma y baja —y en la última fila crea
 *  una nueva—, Tab confirma y pasa a la derecha, Escape descarta la edición.
 *
 *  No guarda nada por su cuenta: solo avisa por `onEditar` de cada celda
 *  confirmada. Quien la usa decide si guarda al vuelo o por tandas (que es lo
 *  que hace el presupuesto, para no disparar una petición por tecla). */
export function RejillaEditable<F>({
  filas,
  columnas,
  idDe,
  nivelDe,
  claseDe,
  onEditar,
  onNuevaFila,
  onEliminarFila,
  onIndentar,
  onSeleccionar,
  seleccionadaId,
  acciones,
  vacia,
}: Props<F>) {
  const [activa, setActiva] = useState<{ f: number; c: number } | null>(null)
  const [editando, setEditando] = useState(false)
  const [borrador, setBorrador] = useState('')
  const [sugerencias, setSugerencias] = useState<OpcionCelda[]>([])
  const [sugerenciaActiva, setSugerenciaActiva] = useState(0)
  const contenedorRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const esEditable = useCallback(
    (fila: F, columna: ColumnaRejilla<F>) => columna.editable?.(fila) ?? false,
    [],
  )

  // Si la fila activa desaparece (se borró, o cambió el filtro), no dejar el
  // cursor apuntando a un índice que ya no existe.
  useEffect(() => {
    if (activa && activa.f >= filas.length) {
      setActiva(filas.length > 0 ? { f: filas.length - 1, c: activa.c } : null)
      setEditando(false)
    }
  }, [filas.length, activa])

  useEffect(() => {
    if (editando) inputRef.current?.focus()
  }, [editando])

  function irA(f: number, c: number) {
    const filaDestino = Math.max(0, Math.min(filas.length - 1, f))
    const colDestino = Math.max(0, Math.min(columnas.length - 1, c))
    setActiva({ f: filaDestino, c: colDestino })
    setEditando(false)
    onSeleccionar?.(filas[filaDestino] ?? null)
    contenedorRef.current?.focus()
  }

  function empezarEdicion(valorInicial?: string) {
    if (!activa) return
    const fila = filas[activa.f]
    const columna = columnas[activa.c]
    if (!fila || !columna || !esEditable(fila, columna)) return
    setBorrador(valorInicial ?? columna.valor(fila))
    setSugerencias([])
    setSugerenciaActiva(0)
    setEditando(true)
  }

  function confirmar(opcion?: OpcionCelda) {
    if (!activa) return
    const fila = filas[activa.f]
    const columna = columnas[activa.c]
    if (fila && columna) onEditar(fila, columna.id, opcion?.valor ?? borrador, opcion)
    setEditando(false)
    setSugerencias([])
    contenedorRef.current?.focus()
  }

  function cancelar() {
    setEditando(false)
    setSugerencias([])
    contenedorRef.current?.focus()
  }

  // --- Modo navegación ---
  function alPulsarNavegando(e: React.KeyboardEvent) {
    if (!activa) {
      if (filas.length > 0 && (e.key === 'ArrowDown' || e.key === 'Tab')) {
        e.preventDefault()
        irA(0, 0)
      }
      return
    }
    const fila = filas[activa.f]

    if (e.altKey && (e.key === 'ArrowRight' || e.key === 'ArrowLeft') && onIndentar && fila) {
      e.preventDefault()
      onIndentar(fila, e.key === 'ArrowRight' ? 1 : -1)
      return
    }
    if (e.ctrlKey && e.key === 'Enter' && onNuevaFila) {
      e.preventDefault()
      onNuevaFila(fila ?? null)
      return
    }
    if (e.ctrlKey && e.key === 'Delete' && onEliminarFila && fila) {
      e.preventDefault()
      onEliminarFila(fila)
      return
    }

    switch (e.key) {
      case 'ArrowUp':
        e.preventDefault()
        irA(activa.f - 1, activa.c)
        return
      case 'ArrowDown':
        e.preventDefault()
        irA(activa.f + 1, activa.c)
        return
      case 'ArrowLeft':
        e.preventDefault()
        irA(activa.f, activa.c - 1)
        return
      case 'ArrowRight':
        e.preventDefault()
        irA(activa.f, activa.c + 1)
        return
      case 'Home':
        e.preventDefault()
        irA(activa.f, 0)
        return
      case 'End':
        e.preventDefault()
        irA(activa.f, columnas.length - 1)
        return
      case 'Tab':
        e.preventDefault()
        if (e.shiftKey) {
          if (activa.c === 0) irA(activa.f - 1, columnas.length - 1)
          else irA(activa.f, activa.c - 1)
        } else {
          if (activa.c === columnas.length - 1) irA(activa.f + 1, 0)
          else irA(activa.f, activa.c + 1)
        }
        return
      case 'F2':
        e.preventDefault()
        empezarEdicion()
        return
      case 'Enter': {
        e.preventDefault()
        const columna = columnas[activa.c]
        if (fila && columna && esEditable(fila, columna)) empezarEdicion()
        else if (activa.f === filas.length - 1 && onNuevaFila) onNuevaFila(fila ?? null)
        else irA(activa.f + 1, activa.c)
        return
      }
      case 'Delete': {
        e.preventDefault()
        const columna = columnas[activa.c]
        if (fila && columna && esEditable(fila, columna)) onEditar(fila, columna.id, '')
        return
      }
      default:
        break
    }

    // Empezar a teclear entra en edición, como en una hoja de cálculo.
    if (!e.ctrlKey && !e.altKey && !e.metaKey && !TECLAS_CONTROL.has(e.key) && e.key.length === 1) {
      e.preventDefault()
      empezarEdicion(e.key)
    }
  }

  // --- Modo edición ---
  function alPulsarEditando(e: React.KeyboardEvent) {
    const columna = activa ? columnas[activa.c] : null
    const hayLista = columna?.tipo === 'autocompletado' && sugerencias.length > 0

    if (hayLista && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault()
      setSugerenciaActiva((i) => {
        const siguiente = e.key === 'ArrowDown' ? i + 1 : i - 1
        return Math.max(0, Math.min(sugerencias.length - 1, siguiente))
      })
      return
    }

    switch (e.key) {
      case 'Enter':
        e.preventDefault()
        if (hayLista) {
          confirmar(sugerencias[sugerenciaActiva])
        } else {
          confirmar()
        }
        if (activa) {
          if (activa.f === filas.length - 1 && onNuevaFila) onNuevaFila(filas[activa.f] ?? null)
          else irA(activa.f + 1, activa.c)
        }
        return
      case 'Tab':
        e.preventDefault()
        confirmar(hayLista ? sugerencias[sugerenciaActiva] : undefined)
        if (activa) {
          if (e.shiftKey) irA(activa.f, activa.c - 1)
          else if (activa.c === columnas.length - 1) irA(activa.f + 1, 0)
          else irA(activa.f, activa.c + 1)
        }
        return
      case 'Escape':
        e.preventDefault()
        cancelar()
        return
      default:
        break
    }
  }

  // Búsqueda del autocompletado, con un respiro para no consultar por tecla.
  useEffect(() => {
    if (!editando || !activa) return
    const columna = columnas[activa.c]
    const fila = filas[activa.f]
    if (columna?.tipo !== 'autocompletado' || !columna.buscar || !fila) return

    let cancelado = false
    const temporizador = setTimeout(() => {
      void columna
        .buscar!(borrador, fila)
        .then((resultado) => {
          if (!cancelado) {
            setSugerencias(resultado)
            setSugerenciaActiva(0)
          }
        })
        .catch(() => {
          if (!cancelado) setSugerencias([])
        })
    }, 200)
    return () => {
      cancelado = true
      clearTimeout(temporizador)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [borrador, editando, activa?.f, activa?.c])

  if (filas.length === 0 && vacia) return <>{vacia}</>

  return (
    <div
      className="rejilla"
      ref={contenedorRef}
      tabIndex={0}
      onKeyDown={(e) => {
        if (!editando) alPulsarNavegando(e)
      }}
    >
      <table className="table rejilla__tabla">
        <thead>
          <tr>
            {columnas.map((col) => (
              <th
                key={col.id}
                style={{ width: col.ancho }}
                className={col.tipo === 'numero' ? 'table__num' : undefined}
              >
                {col.etiqueta}
              </th>
            ))}
            {acciones && <th className="table__actions" />}
          </tr>
        </thead>
        <tbody>
          {filas.map((fila, f) => {
            const id = idDe(fila)
            const nivel = nivelDe?.(fila) ?? 0
            const clases = ['rejilla__fila']
            const propia = claseDe?.(fila)
            if (propia) clases.push(propia)
            if (id === seleccionadaId) clases.push('is-seleccionada')

            return (
              <tr key={id} className={clases.join(' ')}>
                {columnas.map((col, c) => {
                  const esActiva = activa?.f === f && activa?.c === c
                  const editableAqui = esEditable(fila, col)
                  const clasesCelda = ['rejilla__celda']
                  if (col.tipo === 'numero') clasesCelda.push('table__num')
                  if (esActiva) clasesCelda.push('is-activa')
                  if (!editableAqui) clasesCelda.push('is-bloqueada')

                  return (
                    <td
                      key={col.id}
                      className={clasesCelda.join(' ')}
                      style={col.sangrada ? { paddingLeft: `calc(var(--sp-3) + ${nivel} * 18px)` } : undefined}
                      onMouseDown={() => {
                        if (!esActiva || !editando) irA(f, c)
                      }}
                      onDoubleClick={() => editableAqui && empezarEdicion()}
                    >
                      {esActiva && editando ? (
                        col.tipo === 'select' ? (
                          <select
                            className="input input--celda"
                            value={borrador}
                            autoFocus
                            onChange={(e) => {
                              const opcion = col
                                .opciones?.(fila)
                                .find((o) => o.valor === e.target.value)
                              setBorrador(e.target.value)
                              confirmar(opcion ?? { valor: e.target.value, etiqueta: e.target.value })
                            }}
                            onKeyDown={alPulsarEditando}
                            onBlur={() => cancelar()}
                          >
                            {col.opciones?.(fila).map((o) => (
                              <option key={o.valor} value={o.valor}>
                                {o.etiqueta}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="rejilla__editor">
                            <input
                              ref={inputRef}
                              className="input input--celda"
                              type={col.tipo === 'numero' ? 'number' : 'text'}
                              step={col.tipo === 'numero' ? 'any' : undefined}
                              value={borrador}
                              onChange={(e) => setBorrador(e.target.value)}
                              onKeyDown={alPulsarEditando}
                              onBlur={() => confirmar()}
                            />
                            {col.tipo === 'autocompletado' && sugerencias.length > 0 && (
                              <div className="rejilla__sugerencias">
                                {sugerencias.map((s, i) => (
                                  <button
                                    key={s.valor}
                                    type="button"
                                    className={
                                      i === sugerenciaActiva
                                        ? 'rejilla__sugerencia is-activa'
                                        : 'rejilla__sugerencia'
                                    }
                                    // mousedown, no click: el blur del input
                                    // llegaría antes y cerraría la lista.
                                    onMouseDown={(e) => {
                                      e.preventDefault()
                                      confirmar(s)
                                    }}
                                  >
                                    <span className={s.esAccion ? 'rejilla__sugerencia-accion' : undefined}>
                                      {s.etiqueta}
                                    </span>
                                    {s.detalle && <span className="muted">{s.detalle}</span>}
                                  </button>
                                ))}
                              </div>
                            )}
                          </span>
                        )
                      ) : (
                        col.valor(fila) || <span className="muted">—</span>
                      )}
                    </td>
                  )
                })}
                {acciones && <td className="table__actions">{acciones(fila)}</td>}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
