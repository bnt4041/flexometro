import type { ReactNode } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { useEscapeCierra } from './ui'

export interface OpcionCelda {
  valor: string
  etiqueta: string
  /** Texto secundario a la derecha (código, precio…). */
  detalle?: string
  /** Para "crear nuevo" y demás opciones que no salen de la búsqueda. */
  esAccion?: boolean
}

export interface ItemMenuContextual {
  id: string
  etiqueta: string
  icono?: ReactNode
  onClick: () => void
  peligroso?: boolean
  disabled?: boolean
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
  /** Ya formateado por quien la usa (Fase 1f) — se pinta bajo la etiqueta de
   *  la columna, en la propia cabecera. `undefined` no pinta nada; una
   *  columna sin total pero con filtro no debe dejar un hueco en blanco. */
  total?: string
  /** `false` quita la caja de "Filtrar…" de esta columna en la fila de
   *  filtros (Fase 1f). Por defecto todas la tienen. */
  filtrable?: boolean
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
  /** El conjunto de filas marcadas (Mayús+clic o Ctrl/Cmd+clic para varias
   *  sueltas, Mayús+flecha por teclado) — la base para copiar/arrastrar
   *  varias a la vez. Se llama cada vez que cambia; nunca con el conjunto
   *  vacío, que se representa como "nada marcado" sin más. */
  onMarcarVarias?: (ids: string[]) => void
  /** Ctrl/Cmd+C con el foco en la rejilla (no editando una celda): ids de las
   *  filas marcadas, o solo la activa si no hay marca. */
  onCopiar?: (ids: string[]) => void
  /** Ctrl/Cmd+V con el foco en la rejilla. No depende de que haya nada
   *  activo — pegar tiene sentido incluso con la rejilla vacía. */
  onPegar?: () => void
  /** Arrastrar y soltar (Fase 1d/1i): al soltar sobre esta fila (`null` si
   *  se suelta sobre la rejilla vacía o en la franja bajo la última fila,
   *  sin ninguna fila real). Coger la fila (`onDragStart`) ya usa `onCopiar`
   *  tal cual —es la misma foto que Ctrl+C—, así que solo hace falta este
   *  evento nuevo para el destino. `zona` dice DÓNDE dentro de esa fila:
   *  `'dentro'` (soltar en el centro) es el comportamiento de siempre —
   *  meterlo en la fila como contenedor—; `'antes'`/`'despues'` (soltar
   *  cerca del borde superior/inferior) pide colocarlo como hermano de esa
   *  fila, justo antes o después, para reordenar sin cambiar de capítulo.
   *  Sin `onSoltarEn` las filas no se pueden arrastrar. */
  onSoltarEn?: (fila: F | null, zona: 'antes' | 'despues' | 'dentro') => void
  /** Soltar uno o varios ficheros del sistema operativo sobre esta fila
   *  ("Arrastrar al presupuesto") — un `DataTransfer` con `types` incluyendo
   *  `"Files"`, muy distinto de arrastrar una fila propia (`onSoltarEn`),
   *  aunque comparten el mismo gesto visual. Sin `onSoltarFichero` un
   *  fichero soltado aquí no hace nada especial (lo abriría el navegador,
   *  como en cualquier web). */
  onSoltarFichero?: (fila: F, archivos: File[]) => void
  /** Filas que no tiene sentido coger (un capítulo en vez de una partida, la
   *  fila de borrador de un alta en marcha…). Por defecto, todas se pueden
   *  arrastrar; devolver `false` aquí también las deja fuera de `onCopiar`. */
  puedeArrastrar?: (fila: F) => boolean
  /** Clic derecho sobre una fila: qué acciones ofrecerle. `null`/`[]` no
   *  abre menú (deja pasar el menú nativo del navegador). Antes de abrirlo
   *  se selecciona la fila, igual que un clic normal. */
  menuContextual?: (fila: F) => ItemMenuContextual[] | null
  /** Clic derecho en el hueco por debajo de la última fila (o en toda la
   *  rejilla si está vacía) — para acciones que no cuelgan de ninguna fila en
   *  concreto, como "pegar a nivel raíz". */
  menuVacio?: () => ItemMenuContextual[] | null
  acciones?: (fila: F) => ReactNode
  vacia?: ReactNode
  /** Abre esta celda en edición desde fuera (un botón "+ Línea" que crea una
   *  fila fuera del teclado, por ejemplo) — id de fila y de columna, o `null`
   *  para no forzar nada. Cambiar de columna con la misma fila reabre. */
  filaAEditarId?: string | null
  columnaAEditarId?: string | null
  /** Fila de filtros bajo la cabecera (Fase 1f), uno por columna. Sin esto no
   *  se pinta ninguna caja. El filtrado en sí no lo hace esta rejilla —
   *  `filas` ya llega filtrada por quien la usa; esto solo pinta la caja y
   *  avisa de cada tecleo por `onFiltrar`. */
  filtros?: Record<string, string>
  onFiltrar?: (columnaId: string, valor: string) => void
}

/** Se monta solo mientras el menú contextual está abierto, para que
 *  `useEscapeCierra` empuje y saque su capa exactamente en ese momento — si
 *  se llamara sin condición dentro de `RejillaEditable` (que vive montada
 *  todo el rato), su capa se colaría por encima de la de la ficha desde el
 *  principio y un Escape pensado para cerrar la ficha se lo comería el
 *  menú, aunque no hubiera ninguno abierto. */
function CapaEscapeMenu({ onCerrar }: { onCerrar: () => void }) {
  useEscapeCierra(onCerrar)
  return null
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
  onMarcarVarias,
  onCopiar,
  onPegar,
  onSoltarEn,
  onSoltarFichero,
  puedeArrastrar,
  menuContextual,
  menuVacio,
  acciones,
  vacia,
  filaAEditarId,
  columnaAEditarId,
  filtros,
  onFiltrar,
}: Props<F>) {
  const [activa, setActiva] = useState<{ f: number; c: number } | null>(null)
  const [editando, setEditando] = useState(false)
  // Varias filas marcadas a la vez (Fase 1a de arrastrar/copiar): un
  // conjunto de ids, más el índice "ancla" desde el que Mayús+clic o
  // Mayús+flecha extiende el rango. Separado de `activa`, que sigue siendo
  // la única celda con foco de teclado/edición.
  const [marcadas, setMarcadas] = useState<Set<string>>(new Set())
  const anclaMarcado = useRef<number | null>(null)
  // Arrastrar y soltar (Fase 1d): índices de fila, no ids — no hace falta
  // que sobrevivan a que la lista cambie a mitad de un arrastre.
  const [arrastrando, setArrastrando] = useState<number | null>(null)
  const [sobreDestino, setSobreDestino] = useState<number | null>(null)
  // Solo importa junto a `sobreDestino`: en qué tercio de esa fila está el
  // cursor ahora mismo (ver `onSoltarEn`).
  const [zonaDestino, setZonaDestino] = useState<'antes' | 'despues' | 'dentro'>('dentro')
  // Menú contextual (clic derecho): posición en coordenadas de ventana,
  // portado a `document.body` por el mismo motivo que `.rejilla__sugerencias`
  // (ver ese comentario en el CSS) — sin el portal, un widget con zoom que
  // ponga `transform` en un ancestro recortaría el menú.
  const [menu, setMenu] = useState<{ f: number; x: number; y: number } | null>(null)
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

  // Si una fila marcada desaparece (se borró, o se aplicó lo que fuera que
  // estaba marcado), que no quede colgado su id — evita que un futuro
  // pegado/arrastre lo intente usar.
  useEffect(() => {
    setMarcadas((actuales) => {
      if (actuales.size === 0) return actuales
      const vivos = new Set(filas.map(idDe))
      const filtradas = new Set([...actuales].filter((id) => vivos.has(id)))
      return filtradas.size === actuales.size ? actuales : filtradas
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filas])

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

  // Se avisa hacia fuera solo cuando cambia de verdad — evita un aviso en
  // cada tecla mientras se navega sin tocar la marca.
  useEffect(() => {
    onMarcarVarias?.([...marcadas])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marcadas])

  function marcarSolo(f: number) {
    anclaMarcado.current = f
    const fila = filas[f]
    setMarcadas(fila ? new Set([idDe(fila)]) : new Set())
  }

  function extenderMarcado(f: number) {
    const ancla = anclaMarcado.current ?? f
    const desde = Math.max(0, Math.min(ancla, f))
    const hasta = Math.min(filas.length - 1, Math.max(ancla, f))
    const nueva = new Set<string>()
    for (let i = desde; i <= hasta; i++) nueva.add(idDe(filas[i]))
    setMarcadas(nueva)
  }

  function alternarMarcado(f: number) {
    anclaMarcado.current = f
    const fila = filas[f]
    if (!fila) return
    const id = idDe(fila)
    setMarcadas((actual) => {
      const nueva = new Set(actual)
      if (nueva.has(id)) nueva.delete(id)
      else nueva.add(id)
      return nueva
    })
  }

  /** Mueve el cursor de celda. Sin `modo`, deja marcada solo la fila de
   *  destino — es lo que se espera al navegar sin Mayús/Ctrl, igual que en
   *  Excel: cualquier movimiento "normal" limpia una marca de varias filas
   *  anterior. */
  function irA(f: number, c: number, modo?: 'extender' | 'alternar') {
    const filaDestino = Math.max(0, Math.min(filas.length - 1, f))
    const colDestino = Math.max(0, Math.min(maxCol, c))
    setActiva({ f: filaDestino, c: colDestino })
    setEditando(false)
    if (modo === 'extender') extenderMarcado(filaDestino)
    else if (modo === 'alternar') alternarMarcado(filaDestino)
    else marcarSolo(filaDestino)
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
    // Van antes que el `if (!activa)`: pegar tiene sentido con la rejilla
    // vacía (crear la primera fila desde lo copiado), y copiar solo hace
    // falta que haya algo marcado o activo, no ambas cosas a la vez.
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v' && onPegar) {
      e.preventDefault()
      onPegar()
      return
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c' && onCopiar) {
      const filaActiva = activa ? filas[activa.f] : undefined
      const ids = marcadas.size > 0 ? [...marcadas] : filaActiva ? [idDe(filaActiva)] : []
      if (ids.length > 0) {
        e.preventDefault()
        onCopiar(ids)
      }
      return
    }
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
        if (e.shiftKey) irA(activa.f - 1, activa.c, 'extender')
        else irA(activa.f - 1, activa.c)
        return
      case 'ArrowDown':
        e.preventDefault()
        // Mayús+abajo extiende la marca; sin Mayús, en la última fila crea
        // una nueva — extenderla no debería disparar un alta.
        if (e.shiftKey) irA(activa.f + 1, activa.c, 'extender')
        else void bajarOCrear(activa.f, activa.c)
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
      case 'Escape':
        // Solo si hay de verdad varias filas marcadas: si no, Esc no es cosa
        // de la rejilla y tiene que subir a cerrar la ficha, como siempre.
        if (marcadas.size > 1) {
          e.preventDefault()
          e.stopPropagation()
          marcarSolo(activa.f)
        }
        return
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

  // El Escape lo gestiona `useEscapeCierra` más abajo (vía `CapaEscapeMenu`),
  // no aquí: esta rejilla suele vivir dentro de una ficha que TAMBIÉN se
  // cierra con Escape, y sin repartirlo por la pila de capas un Escape para
  // cerrar solo el menú se llevaría la ficha entera por delante.
  useEffect(() => {
    if (!menu) return
    function alPulsarFuera(e: MouseEvent) {
      const nodo = e.target as Node
      if (!(nodo instanceof Element) || !nodo.closest('.rejilla__menu-contextual')) setMenu(null)
    }
    document.addEventListener('mousedown', alPulsarFuera)
    return () => {
      document.removeEventListener('mousedown', alPulsarFuera)
    }
  }, [menu])

  // Ojo: aunque no haya filas, el contenedor con el `onKeyDown` tiene que
  // seguir montado — si no, Ctrl+V no tiene dónde engancharse y pegar en una
  // rejilla vacía (el caso más típico: la primera vez que se pega algo aquí)
  // no funcionaría nunca.
  if (filas.length === 0 && vacia) {
    return (
      <div
        className={sobreDestino === -1 ? 'rejilla is-destino-arrastre' : 'rejilla'}
        ref={contenedorRef}
        tabIndex={0}
        onMouseDown={() => contenedorRef.current?.focus()}
        onKeyDown={(e) => {
          if (!editando) alPulsarNavegando(e)
        }}
        onDragOver={(e) => {
          if (!onSoltarEn) return
          e.preventDefault()
          if (sobreDestino !== -1) setSobreDestino(-1)
        }}
        onDragLeave={() => setSobreDestino((actual) => (actual === -1 ? null : actual))}
        onDrop={(e) => {
          e.preventDefault()
          setSobreDestino(null)
          onSoltarEn?.(null, 'dentro')
        }}
      >
        {vacia}
      </div>
    )
  }

  return (
    <div
      className="rejilla"
      ref={contenedorRef}
      tabIndex={0}
      onKeyDown={(e) => {
        if (!editando) alPulsarNavegando(e)
      }}
      onContextMenu={(e) => {
        // Solo el hueco por debajo de la última fila: un clic derecho sobre
        // una fila de verdad ya lo resuelve su propio `onContextMenu` (y
        // frena la propagación antes de llegar aquí).
        if (!menuVacio || (e.target as Element).closest('tr')) return
        const items = menuVacio()
        if (!items || items.length === 0) return
        e.preventDefault()
        setMenu({ f: -1, x: e.clientX, y: e.clientY })
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
                {col.total !== undefined && <div className="rejilla__total-columna">{col.total}</div>}
              </th>
            ))}
            {acciones && <th className="table__actions" />}
          </tr>
          {(filtros || onFiltrar) && (
            <tr className="rejilla__fila-filtros">
              {columnas.map((col) => (
                <th key={col.id}>
                  {col.filtrable !== false && (
                    <input
                      type="text"
                      className="rejilla__filtro-input"
                      placeholder="Filtrar…"
                      value={filtros?.[col.id] ?? ''}
                      onChange={(e) => onFiltrar?.(col.id, e.target.value)}
                    />
                  )}
                </th>
              ))}
              {acciones && <th />}
            </tr>
          )}
        </thead>
        <tbody>
          {filas.map((fila, f) => {
            const id = idDe(fila)
            const nivel = nivelDe?.(fila) ?? 0
            const clases = ['rejilla__fila']
            const propia = claseDe?.(fila)
            if (propia) clases.push(propia)
            if (id === seleccionadaId) clases.push('is-seleccionada')
            // Distinta de `is-seleccionada` (esa es "la partida que siguen
            // los demás widgets", una sola). Esta es "están marcadas para
            // copiar/arrastrar juntas", puede ser ninguna, una o varias.
            if (marcadas.has(id)) clases.push('is-marcada')
            if (arrastrando === f) clases.push('is-arrastrando')
            if (sobreDestino === f && arrastrando !== f) {
              clases.push(
                zonaDestino === 'dentro' ? 'is-destino-arrastre' : `is-destino-arrastre-${zonaDestino}`,
              )
            }
            const filaEditandoseAqui = editando && activa?.f === f
            const arrastrableAqui = Boolean(onCopiar) && !filaEditandoseAqui && (puedeArrastrar?.(fila) ?? true)

            return (
              <tr
                key={id}
                className={clases.join(' ')}
                draggable={arrastrableAqui}
                onDragStart={(e) => {
                  const yaMarcada = marcadas.has(id)
                  if (!yaMarcada) marcarSolo(f)
                  const idsArrastre = yaMarcada ? [...marcadas] : [id]
                  setArrastrando(f)
                  e.dataTransfer.effectAllowed = 'copyMove'
                  // Firefox exige `setData` con algo para dejar arrastrar.
                  e.dataTransfer.setData('text/plain', id)
                  onCopiar?.(idsArrastre)
                }}
                onDragEnd={() => {
                  setArrastrando(null)
                  setSobreDestino(null)
                }}
                onDragOver={(e) => {
                  // Un fichero del sistema operativo, no una fila propia
                  // arrastrada dentro de la rejilla — comparten el mismo
                  // gesto pero son dos cosas distintas (ver `onSoltarFichero`).
                  if (e.dataTransfer.types.includes('Files')) {
                    if (!onSoltarFichero) return
                    e.preventDefault()
                    if (sobreDestino !== f) setSobreDestino(f)
                    return
                  }
                  if (!onSoltarEn || arrastrando === null) return
                  // Sin esto el navegador no deja soltar: por defecto un
                  // `dragover` no autoriza el `drop` que le sigue.
                  e.preventDefault()
                  // Tercio superior/inferior de la fila: reordenar como
                  // hermano ("antes"/"despues"); el tercio central mantiene
                  // el comportamiento de siempre ("dentro", como contenedor).
                  const rect = e.currentTarget.getBoundingClientRect()
                  const relativa = (e.clientY - rect.top) / rect.height
                  const zona = relativa < 1 / 3 ? 'antes' : relativa > 2 / 3 ? 'despues' : 'dentro'
                  if (sobreDestino !== f) setSobreDestino(f)
                  if (zonaDestino !== zona) setZonaDestino(zona)
                }}
                onDrop={(e) => {
                  e.preventDefault()
                  setArrastrando(null)
                  setSobreDestino(null)
                  if (e.dataTransfer.types.includes('Files')) {
                    const archivos = Array.from(e.dataTransfer.files)
                    if (archivos.length > 0 && onSoltarFichero) onSoltarFichero(fila, archivos)
                    return
                  }
                  onSoltarEn?.(fila, zonaDestino)
                }}
                onContextMenu={(e) => {
                  if (!menuContextual) return
                  const items = menuContextual(fila)
                  if (!items || items.length === 0) return
                  e.preventDefault()
                  // Sin esto, el `onContextMenu` del contenedor (más abajo,
                  // para `menuVacio`) se dispara también y pisa este menú.
                  e.stopPropagation()
                  // Si la fila ya estaba marcada, el botón derecho no debe
                  // colapsar la selección múltiple — se respeta tal cual para
                  // que el menú pueda actuar sobre todo el grupo.
                  if (!marcadas.has(id)) irA(f, 0)
                  setMenu({ f, x: e.clientX, y: e.clientY })
                }}
              >
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
                      onMouseDown={(e) => {
                        if (esActiva && editando) return
                        // El botón derecho no debe tocar la marca aquí: si
                        // cae sobre una fila ya marcada, `onContextMenu` (más
                        // abajo, en el `<tr>`) tiene que verla intacta para
                        // poder abrir el menú sobre todo el grupo.
                        if (e.button !== 0) return
                        if (e.shiftKey) {
                          // Evita que el navegador arrastre una selección de
                          // texto nativa mientras se marca con Mayús.
                          e.preventDefault()
                          irA(f, c, 'extender')
                        } else if (e.ctrlKey || e.metaKey) {
                          e.preventDefault()
                          irA(f, c, 'alternar')
                        } else if (!marcadas.has(id)) {
                          // Si la fila ya estaba marcada (posible selección
                          // múltiple), no se colapsa aquí todavía: podría ser
                          // el inicio de arrastrar el grupo entero. Si no era
                          // un arrastre, `onClick` — que el navegador no
                          // dispara cuando sí lo hubo — la deja en esta sola.
                          irA(f, c)
                        }
                      }}
                      onClick={(e) => {
                        if (e.shiftKey || e.ctrlKey || e.metaKey) return
                        if (marcadas.has(id)) irA(f, c)
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
          {onSoltarEn && (
            // Soltar por debajo de la última fila arrastrable tenía que
            // caer en algún elemento con su propio `onDrop` — sin esto, el
            // navegador resolvía el drop contra la última fila de verdad
            // (normalmente un capítulo), así que "mover a la raíz" acababa
            // moviendo dentro de ese capítulo en vez de al nivel raíz. Vacía
            // a propósito: solo existe como zona de destino, `vacia` ya
            // cubre el mensaje para cuando no hay ninguna fila.
            <tr
              className={sobreDestino === -1 ? 'rejilla__fila-raiz is-destino-arrastre' : 'rejilla__fila-raiz'}
              onDragOver={(e) => {
                if (arrastrando === null || e.dataTransfer.types.includes('Files')) return
                e.preventDefault()
                if (sobreDestino !== -1) setSobreDestino(-1)
              }}
              onDragLeave={() => setSobreDestino((actual) => (actual === -1 ? null : actual))}
              onDrop={(e) => {
                e.preventDefault()
                setArrastrando(null)
                setSobreDestino(null)
                onSoltarEn(null, 'dentro')
              }}
            >
              <td colSpan={columnas.length + (acciones ? 1 : 0)} />
            </tr>
          )}
        </tbody>
      </table>
      {menu &&
        (() => {
          const items = menu.f === -1 ? menuVacio?.() : menuContextual?.(filas[menu.f])
          if (!items || items.length === 0) return null
          return (
            <>
              <CapaEscapeMenu onCerrar={() => setMenu(null)} />
              {createPortal(
                <div
                  className="rejilla__menu-contextual"
                  role="menu"
                  style={{ top: menu.y, left: menu.x }}
                >
                  {items.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      role="menuitem"
                      disabled={item.disabled}
                      className={
                        item.peligroso
                          ? 'rejilla__menu-contextual-item is-peligroso'
                          : 'rejilla__menu-contextual-item'
                      }
                      onClick={() => {
                        setMenu(null)
                        item.onClick()
                      }}
                    >
                      {item.icono}
                      {item.etiqueta}
                    </button>
                  ))}
                </div>,
                document.body,
              )}
            </>
          )
        })()}
    </div>
  )
}
