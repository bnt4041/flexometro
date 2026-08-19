import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

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
  /** Adorno a la izquierda del valor cuando la celda no se está editando —
   *  el desplegable de replegar el árbol, por ejemplo. Recibe los clics por su
   *  cuenta, así que debe frenar la propagación si no quiere mover el cursor. */
  prefijo?: (fila: F) => ReactNode
}

interface Props<F> {
  filas: F[]
  columnas: ColumnaRejilla<F>[]
  idDe: (fila: F) => string
  nivelDe?: (fila: F) => number
  claseDe?: (fila: F) => string | undefined
  /** Se llama al confirmar una celda. `opcion` viene relleno en select/autocompletado. */
  onEditar: (fila: F, columnaId: string, valor: string, opcion?: OpcionCelda) => void
  /** Puede devolver una promesa: la rejilla espera a que la fila exista para
   *  bajar el cursor a ella, y evita crear dos si se insiste con la tecla. */
  onNuevaFila?: (filaActual: F | null) => void | Promise<void>
  onEliminarFila?: (fila: F) => void
  /** +1 indenta (Alt+→), -1 desindenta (Alt+←). */
  onIndentar?: (fila: F, direccion: 1 | -1) => void
  onSeleccionar?: (fila: F | null) => void
  seleccionadaId?: string | null
  acciones?: (fila: F) => ReactNode
  vacia?: ReactNode
  /** Abre esta celda en edición desde fuera (un botón "+ Línea" que crea una
   *  fila fuera del teclado, por ejemplo) — id de fila y de columna, o `null`
   *  para no forzar nada. Cambiar de columna con la misma fila reabre. */
  filaAEditarId?: string | null
  columnaAEditarId?: string | null
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
  filaAEditarId,
  columnaAEditarId,
}: Props<F>) {
  const [activa, setActiva] = useState<{ f: number; c: number } | null>(null)
  const [editando, setEditando] = useState(false)
  const [borrador, setBorrador] = useState('')
  const [sugerencias, setSugerencias] = useState<OpcionCelda[]>([])
  const [sugerenciaActiva, setSugerenciaActiva] = useState(0)
  const [posicionSugerencias, setPosicionSugerencias] = useState<{
    top: number
    left: number
    width: number
  } | null>(null)
  const contenedorRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const editorRef = useRef<HTMLSpanElement>(null)
  // Al salir de edición React desmonta el input, y eso dispara su `blur`. Sin
  // esta marca, cancelar con Escape acabaría guardando por la puerta de atrás.
  const cancelando = useRef(false)
  const confirmando = useRef(false)
  // Crear una fila es un viaje al servidor: sin esta marca, mantener pulsada
  // la flecha abajo al final de la tabla dispararía varias altas seguidas.
  const creando = useRef(false)
  // Adónde llevar el cursor en cuanto la fila recién creada aparezca.
  const destinoTrasCrear = useRef<{ f: number; c: number } | null>(null)
  const seleccionarAlEditar = useRef(false)
  // Qué combinación fila+columna de `filaAEditarId`/`columnaAEditarId` ya se
  // abrió, para no reabrirla en cada render (esas props llegan como valores
  // nuevos cada vez que el padre recalcula `filas`/`columnas`).
  const aEditarProcesada = useRef<string | null>(null)

  const esEditable = useCallback(
    (fila: F, columna: ColumnaRejilla<F>) => columna.editable?.(fila) ?? false,
    [],
  )

  // Con `acciones`, hay una columna más al final (sin dato editable, con los
  // botones de la fila) que también se puede alcanzar con flechas/Tab.
  const maxCol = columnas.length - 1 + (acciones ? 1 : 0)
  const esColumnaAcciones = (c: number) => acciones !== undefined && c === columnas.length
  // Referencia a la celda de acciones activa, para poder pulsar su primer
  // botón con Enter sin que `acciones` tenga que exponer un callback aparte.
  const celdaAccionesRef = useRef<HTMLTableCellElement>(null)

  // `columna.valor()` es para mostrar (con el punto de los miles y la coma
  // decimal de `formatoImporte`), pero un `<input type="number">` solo acepta
  // el punto como separador — con una coma dentro se queda en blanco. F2 (o
  // esta misma rejilla abriendo una celda desde fuera) necesitan la versión
  // sin formatear para precargar el campo.
  const valorParaEditar = useCallback(
    (fila: F, columna: ColumnaRejilla<F>) => {
      const texto = columna.valor(fila)
      return columna.tipo === 'numero' ? texto.replaceAll('.', '').replace(',', '.') : texto
    },
    [],
  )

  // Si la fila activa desaparece (se borró, o cambió el filtro), no dejar el
  // cursor apuntando a un índice que ya no existe. Y si veníamos de crear una
  // fila, bajar a ella en cuanto llegue del servidor.
  useEffect(() => {
    const destino = destinoTrasCrear.current
    if (destino && destino.f < filas.length) {
      destinoTrasCrear.current = null
      setActiva(destino)
      setEditando(false)
      contenedorRef.current?.focus()
      return
    }
    if (activa && activa.f >= filas.length) {
      setActiva(filas.length > 0 ? { f: filas.length - 1, c: activa.c } : null)
      setEditando(false)
    }
  }, [filas.length, activa])

  useEffect(() => {
    if (!filaAEditarId || !columnaAEditarId) {
      aEditarProcesada.current = null
      return
    }
    const clave = `${filaAEditarId}:${columnaAEditarId}`
    if (aEditarProcesada.current === clave) return
    const f = filas.findIndex((fila) => idDe(fila) === filaAEditarId)
    const c = columnas.findIndex((col) => col.id === columnaAEditarId)
    if (f < 0 || c < 0) return
    const fila = filas[f]
    const columna = columnas[c]
    if (!fila || !columna || !esEditable(fila, columna)) return
    aEditarProcesada.current = clave
    setActiva({ f, c })
    cancelando.current = false
    seleccionarAlEditar.current = true
    setBorrador(valorParaEditar(fila, columna))
    setSugerencias([])
    setSugerenciaActiva(0)
    setEditando(true)
  }, [filaAEditarId, columnaAEditarId, filas, columnas, idDe, esEditable, valorParaEditar])

  useEffect(() => {
    if (!editando) return
    inputRef.current?.focus()
    // Al abrir la celda con F2/Enter el contenido queda seleccionado, para
    // poder reemplazarlo escribiendo sin tener que borrarlo antes. Si se ha
    // entrado tecleando, el borrador ya es esa tecla y no hay nada que marcar.
    if (seleccionarAlEditar.current) {
      inputRef.current?.select()
      seleccionarAlEditar.current = false
    }
  }, [editando])

  function irA(f: number, c: number) {
    const filaDestino = Math.max(0, Math.min(filas.length - 1, f))
    const colDestino = Math.max(0, Math.min(maxCol, c))
    setActiva({ f: filaDestino, c: colDestino })
    setEditando(false)
    onSeleccionar?.(filas[filaDestino] ?? null)
    contenedorRef.current?.focus()
  }

  /** Baja a la fila siguiente y, si no hay ninguna debajo, crea una. Es lo que
   *  se espera al ir tecleando seguido: la tabla crece sola por abajo. */
  async function bajarOCrear(f: number, c: number) {
    if (f + 1 < filas.length) {
      irA(f + 1, c)
      return
    }
    if (!onNuevaFila || creando.current) return
    creando.current = true
    destinoTrasCrear.current = { f: f + 1, c }
    try {
      await onNuevaFila(filas[f] ?? null)
    } finally {
      creando.current = false
    }
  }

  function empezarEdicion(valorInicial?: string) {
    if (!activa) return
    const fila = filas[activa.f]
    const columna = columnas[activa.c]
    if (!fila || !columna || !esEditable(fila, columna)) return
    cancelando.current = false
    seleccionarAlEditar.current = valorInicial === undefined
    setBorrador(valorInicial ?? valorParaEditar(fila, columna))
    setSugerencias([])
    setSugerenciaActiva(0)
    setEditando(true)
  }

  function confirmar(opcion?: OpcionCelda) {
    if (!activa || cancelando.current || confirmando.current) return
    // El `focus()` de aquí abajo quita el foco del input todavía montado, y
    // eso dispara su `blur` de forma síncrona — que llama a este mismo
    // `confirmar()` otra vez (sin `opcion`, desde `onBlur`) ANTES de que esta
    // llamada termine. Sin el guard, un `onEditar` que reacciona a la opción
    // elegida (crear/enlazar algo) se pisa con una segunda llamada vacía.
    confirmando.current = true
    try {
      const fila = filas[activa.f]
      const columna = columnas[activa.c]
      if (fila && columna) onEditar(fila, columna.id, opcion?.valor ?? borrador, opcion)
      setEditando(false)
      setSugerencias([])
      contenedorRef.current?.focus()
    } finally {
      confirmando.current = false
    }
  }

  function cancelar() {
    cancelando.current = true
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
        void bajarOCrear(activa.f, activa.c)
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
        irA(activa.f, maxCol)
        return
      case 'Tab':
        e.preventDefault()
        if (e.shiftKey) {
          if (activa.c === 0) irA(activa.f - 1, maxCol)
          else irA(activa.f, activa.c - 1)
        } else {
          // Al pasar del último campo se salta a la fila siguiente, y si no
          // hay ninguna, se crea. La columna de acciones (si la hay) cuenta
          // como el último campo, igual que con las flechas.
          if (activa.c === maxCol) void bajarOCrear(activa.f, 0)
          else irA(activa.f, activa.c + 1)
        }
        return
      case 'F2':
        e.preventDefault()
        empezarEdicion()
        return
      case 'Enter': {
        e.preventDefault()
        if (esColumnaAcciones(activa.c)) {
          celdaAccionesRef.current?.querySelector('button')?.click()
          return
        }
        const columna = columnas[activa.c]
        if (fila && columna && esEditable(fila, columna)) empezarEdicion()
        else void bajarOCrear(activa.f, activa.c)
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
        if (activa) void bajarOCrear(activa.f, activa.c)
        return
      case 'Tab':
        e.preventDefault()
        confirmar(hayLista ? sugerencias[sugerenciaActiva] : undefined)
        if (activa) {
          if (e.shiftKey) irA(activa.f, activa.c - 1)
          else if (activa.c === maxCol) void bajarOCrear(activa.f, 0)
          else irA(activa.f, activa.c + 1)
        }
        return
      case 'Escape':
        e.preventDefault()
        // La ficha que envuelve la rejilla cierra con Escape (ver
        // `FichaDetalle`). Mientras se edita una celda, Escape solo descarta
        // esa celda: dejarlo subir cerraría el presupuesto entero a media
        // captura de datos.
        e.stopPropagation()
        cancelar()
        return
      default:
        break
    }
  }

  // La celda vive dentro de una `<td>` con `overflow: hidden` (para el
  // truncado con puntos suspensivos del valor sin editar) y a veces dentro de
  // un widget con zoom (`transform: scale()`, ver `WidgetGrid`), que recorta
  // cualquier hijo posicionado. El listado de sugerencias se posiciona en
  // coordenadas de ventana y se saca por portal (más abajo) para flotar por
  // encima de todo eso en vez de quedar cortado contra esos bordes.
  useEffect(() => {
    if (!editando || sugerencias.length === 0 || !editorRef.current) {
      setPosicionSugerencias(null)
      return
    }
    function recalcular() {
      const r = editorRef.current?.getBoundingClientRect()
      if (r) setPosicionSugerencias({ top: r.bottom + 2, left: r.left, width: r.width })
    }
    recalcular()
    window.addEventListener('scroll', recalcular, true)
    window.addEventListener('resize', recalcular)
    return () => {
      window.removeEventListener('scroll', recalcular, true)
      window.removeEventListener('resize', recalcular)
    }
  }, [editando, sugerencias])

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
                          <span className="rejilla__editor" ref={editorRef}>
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
                            {col.tipo === 'autocompletado' &&
                              sugerencias.length > 0 &&
                              posicionSugerencias &&
                              createPortal(
                                <div
                                  className="rejilla__sugerencias"
                                  style={{
                                    top: posicionSugerencias.top,
                                    left: posicionSugerencias.left,
                                    minWidth: Math.max(320, posicionSugerencias.width),
                                  }}
                                >
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
                                      <span
                                        className={s.esAccion ? 'rejilla__sugerencia-accion' : undefined}
                                      >
                                        {s.etiqueta}
                                      </span>
                                      {s.detalle && <span className="muted">{s.detalle}</span>}
                                    </button>
                                  ))}
                                </div>,
                                document.body,
                              )}
                          </span>
                        )
                      ) : (
                        <>
                          {col.prefijo?.(fila)}
                          {col.valor(fila) || <span className="muted">—</span>}
                        </>
                      )}
                    </td>
                  )
                })}
                {acciones &&
                  (() => {
                    const activaAqui = activa?.f === f && esColumnaAcciones(activa.c)
                    return (
                      <td
                        ref={activaAqui ? celdaAccionesRef : undefined}
                        className={activaAqui ? 'table__actions is-activa' : 'table__actions'}
                        onMouseDown={() => irA(f, columnas.length)}
                      >
                        {acciones(fila)}
                      </td>
                    )
                  })()}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
