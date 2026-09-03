import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown,
  ChevronUp,
  Circle,
  Hand,
  Layers,
  Minus,
  Plus,
  Ruler,
  MousePointerClick,
  Send,
  Sparkles,
  Square,
  StickyNote,
  Trash2,
  Waypoints,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'

import { LienzoPlano } from './LienzoPlano'
import type { Herramienta } from './LienzoPlano'
import { ErrorNotice, Field, Modal, formatoImporte } from './ui'
import { api } from '../lib/api'
import type {
  CapaPlano,
  ElementoPlano,
  LecturaIaPlano,
  PlanoDetalle as Detalle,
  PuntoPlano,
} from '../lib/api'
import { useToast } from '../toast'

const HERRAMIENTAS: { id: Herramienta; etiqueta: string; icono: typeof Hand; soloDxf?: boolean }[] = [
  { id: 'mano', etiqueta: 'Seleccionar', icono: Hand },
  { id: 'entidad', etiqueta: 'Medir una entidad del plano', icono: MousePointerClick, soloDxf: true },
  { id: 'calibrar', etiqueta: 'Calibrar con una cota', icono: Ruler },
  { id: 'longitud', etiqueta: 'Medir longitud', icono: Waypoints },
  { id: 'area', etiqueta: 'Medir área', icono: Square },
  { id: 'conteo', etiqueta: 'Contar', icono: Circle },
  { id: 'auxiliar', etiqueta: 'Línea auxiliar', icono: Minus },
  { id: 'nota', etiqueta: 'Nota', icono: StickyNote },
]

const AYUDA: Record<Herramienta, string> = {
  mano: 'Pincha un elemento para verlo o borrarlo.',
  entidad:
    'Pincha una línea del plano y se mide entera, con su geometría exacta. No hay que ir vértice a vértice.',
  calibrar: 'Pincha los dos extremos de una cota que conozcas y teclea cuánto mide.',
  longitud: 'Pincha los vértices. Doble clic o Enter para cerrar, Esc para descartar.',
  area: 'Pincha el contorno. Doble clic o Enter para cerrar; se cierra solo.',
  conteo: 'Un clic por unidad. Doble clic o Enter para cerrar.',
  auxiliar: 'Dos puntos. No mide: sirve para alinear y replantear.',
  nota: 'Pincha dónde va y escribe el texto.',
}

/** Qué unidad mide cada tipo de elemento — espejo de `UNIDAD_DE` en
 *  `backend/app/modules/planos/enums.py`. Solo para decidir en el cliente si
 *  tiene sentido ofrecer "Aplicar a esta partida" antes de intentarlo; el
 *  backend vuelve a comprobarlo de todas formas (`aplicar_a_partida`). */
const UNIDAD_DEL_TIPO: Partial<Record<ElementoPlano['tipo'], string>> = {
  longitud: 'm',
  area: 'm2',
  conteo: 'ud',
}

function normalizarUnidad(u: string): string {
  return u.toLowerCase().replace('²', '2').replace(/\s+/g, '')
}

function unidadesCompatibles(tipo: ElementoPlano['tipo'], unidadPartida: string): boolean {
  const esperada = UNIDAD_DEL_TIPO[tipo]
  return esperada !== undefined && normalizarUnidad(unidadPartida) === esperada
}

/** Los tipos que miden, igual que `TIPOS_QUE_MIDEN` en el backend: una nota o
 *  una línea auxiliar están dibujadas, pero no son una medición. */
const TIPOS_MEDIBLES: ElementoPlano['tipo'][] = ['longitud', 'area', 'conteo']

/** Cómo llamar a cada cosa dibujada cuando no tiene nombre propio. Sin esto,
 *  una lista de seis áreas sin etiqueta son seis números sueltos sin decir de
 *  qué son. */
const NOMBRE_TIPO: Record<ElementoPlano['tipo'], string> = {
  nota: 'Nota',
  auxiliar: 'Línea auxiliar',
  longitud: 'Longitud',
  area: 'Superficie',
  conteo: 'Conteo',
}

export interface AplicarAPartida {
  partidaId: string
  unidad: string
  /** Ids de `LineaMedicion` que ya tiene ESTA partida — distingue "aplicado
   *  a esta partida" de "aplicado a otra partida de este mismo presupuesto"
   *  sin tener que ampliar el backend solo para eso. */
  idsLineas: Set<string>
}

/** El visor/editor de un plano — Fase 34: calibrar, dibujar y medir encima
 *  de un PDF, imagen o DXF. Extraído de la pantalla `/planos/:id`
 *  (`PlanoDetalle`) para poder incrustarlo también dentro de la pestaña de
 *  Mediciones de una partida (Fase 1k) sin una segunda `ModalPantalla`
 *  anidada — este componente no lleva chrome de página, solo el contenido;
 *  quien lo usa decide si lo envuelve en algo o lo pone tal cual.
 *
 *  Con `aplicarA` (el caso de la partida) cada medición gana un botón para
 *  mandarla como línea de medición de esa partida — reutiliza
 *  `POST /elementos/{id}/aplicar`, que ya existía en el backend sin ningún
 *  sitio en la interfaz que lo llamara. Sin `aplicarA` (el caso de la
 *  biblioteca de planos) se comporta exactamente como antes. */
export function VisorPlano({
  planoId,
  aplicarA,
  onAplicado,
  onCargado,
  autoRevisarIa,
  onRevisado,
}: {
  planoId: string
  aplicarA?: AplicarAPartida
  onAplicado?: () => void
  /** Avisa con el plano en cuanto llega — para que quien envuelve esto (una
   *  `ModalPantalla` con título dinámico, por ejemplo) pueda mostrar su
   *  código/nombre sin tener que pedirlo por su cuenta. */
  onCargado?: (plano: Detalle) => void
  /** Nada más subir un plano que no sea DXF, lo revisa la IA sin esperar a
   *  que se pulse nada — el DXF no lo necesita: llega ya con su geometría y
   *  sus unidades. `onRevisado` avisa en cuanto se ha lanzado (con éxito o
   *  no) para que quien lo puso a `true` lo vuelva a `false` y no se repita
   *  en el siguiente render. */
  autoRevisarIa?: boolean
  onRevisado?: () => void
}) {
  const { notificar } = useToast()

  const [plano, setPlano] = useState<Detalle | null>(null)
  const [hojaId, setHojaId] = useState<string | null>(null)
  const [elementos, setElementos] = useState<ElementoPlano[]>([])
  const [herramienta, setHerramienta] = useState<Herramienta>('mano')
  const [capaActiva, setCapaActiva] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [seleccionado, setSeleccionado] = useState<string | null>(null)
  const [pendiente, setPendiente] = useState<{ tipo: Herramienta; puntos: PuntoPlano[] } | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [lectura, setLectura] = useState<LecturaIaPlano | null>(null)
  const [leyendo, setLeyendo] = useState(false)
  // Cuando la IA ha leído una cota, su valor queda cargado: al pinchar los dos
  // extremos se calibra directamente, sin volver a teclear cuánto mide.
  const [cotaPrefijada, setCotaPrefijada] = useState<string | null>(null)
  // Solo tiene sentido con `aplicarA`: manda cada medición nueva compatible
  // sin esperar a que se pulse "Aplicar" a mano.
  const [autoAplicar, setAutoAplicar] = useState(false)
  const [aplicando, setAplicando] = useState<string | null>(null)
  const [peticionIa, setPeticionIa] = useState('')
  const [puntosEnCurso, setPuntosEnCurso] = useState(0)
  const visorRef = useRef<HTMLDivElement>(null)
  // Al ampliar con la rueda hay que recolocar el scroll para que no se te vaya
  // el plano: se apunta aquí lo que hay que corregir y se aplica cuando el
  // nuevo tamaño ya está en pantalla (`useLayoutEffect`).
  const ajusteScroll = useRef<{ factor: number; x: number; y: number } | null>(null)

  const cargar = useCallback(async () => {
    try {
      const detalle = await api.planos.get(planoId)
      setPlano(detalle)
      // Se comprueba que lo que había elegido siga existiendo, no solo que
      // hubiera algo elegido: al borrar la hoja o la capa activa, quedarse
      // con su id dejaría el visor apuntando a algo que ya no está.
      setHojaId((actual) =>
        actual && detalle.hojas.some((h) => h.id === actual)
          ? actual
          : (detalle.hojas[0]?.id ?? null),
      )
      setCapaActiva((actual) =>
        actual && detalle.capas.some((c) => c.id === actual)
          ? actual
          : (detalle.capas[0]?.id ?? null),
      )
      setError(null)
      onCargado?.(detalle)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [planoId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const cargarElementos = useCallback(async () => {
    if (!hojaId) return
    try {
      setElementos(await api.planos.elementos.list(hojaId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [hojaId])

  useEffect(() => {
    void cargarElementos()
  }, [cargarElementos])

  const hoja = useMemo(
    () => plano?.hojas.find((h) => h.id === hojaId) ?? null,
    [plano, hojaId],
  )
  const calibrada = hoja?.metros_por_unidad != null
  const esVectorial = plano?.origen === 'dxf'

  // Rueda = zoom, y no scroll: en un plano se amplía mucho más a menudo de lo
  // que se baja. Para desplazarse está el botón central, como en cualquier
  // programa de CAD. El listener va a mano y no por `onWheel` de React porque
  // React lo registra como pasivo y `preventDefault()` no surtiría efecto: la
  // página entera haría scroll además de ampliarse.
  useEffect(() => {
    const caja = visorRef.current
    if (!caja) return

    function alRodar(evento: WheelEvent) {
      if (!caja) return
      evento.preventDefault()
      const rect = caja.getBoundingClientRect()
      const x = evento.clientX - rect.left
      const y = evento.clientY - rect.top
      setZoom((actual) => {
        const nuevo = Math.min(
          8,
          Math.max(0.25, Math.round(actual * (evento.deltaY < 0 ? 1.15 : 1 / 1.15) * 100) / 100),
        )
        if (nuevo !== actual) ajusteScroll.current = { factor: nuevo / actual, x, y }
        return nuevo
      })
    }

    let arrastre: { x: number; y: number; scrollLeft: number; scrollTop: number } | null = null

    function alPulsar(evento: MouseEvent) {
      if (evento.button !== 1 || !caja) return
      // Sin esto el navegador entra en su propio modo de desplazamiento
      // automático (la brújula del botón central) y se come el arrastre.
      evento.preventDefault()
      arrastre = {
        x: evento.clientX,
        y: evento.clientY,
        scrollLeft: caja.scrollLeft,
        scrollTop: caja.scrollTop,
      }
      caja.classList.add('is-arrastrando')
    }

    function alMover(evento: MouseEvent) {
      if (!arrastre || !caja) return
      caja.scrollLeft = arrastre.scrollLeft - (evento.clientX - arrastre.x)
      caja.scrollTop = arrastre.scrollTop - (evento.clientY - arrastre.y)
    }

    function alSoltar() {
      arrastre = null
      caja?.classList.remove('is-arrastrando')
    }

    caja.addEventListener('wheel', alRodar, { passive: false })
    caja.addEventListener('mousedown', alPulsar)
    window.addEventListener('mousemove', alMover)
    window.addEventListener('mouseup', alSoltar)
    return () => {
      caja.removeEventListener('wheel', alRodar)
      caja.removeEventListener('mousedown', alPulsar)
      window.removeEventListener('mousemove', alMover)
      window.removeEventListener('mouseup', alSoltar)
    }
    // Depende del plano cargado y no de `[]`: mientras se carga, este
    // componente devuelve un «Cargando…» y el visor no existe todavía en el
    // DOM, así que con `[]` la referencia sería nula y no se engancharía nada.
  }, [plano?.id, hojaId])

  // Mantener bajo el cursor el punto del plano que estaba ahí antes de
  // ampliar. Sin esto, cada golpe de rueda te deja mirando otra parte del
  // plano y hay que buscar otra vez dónde estabas.
  useLayoutEffect(() => {
    const caja = visorRef.current
    const ajuste = ajusteScroll.current
    if (!caja || !ajuste) return
    ajusteScroll.current = null
    caja.scrollLeft = (caja.scrollLeft + ajuste.x) * ajuste.factor - ajuste.x
    caja.scrollTop = (caja.scrollTop + ajuste.y) * ajuste.factor - ajuste.y
  }, [zoom])

  async function aplicar(elementoId: string) {
    if (!aplicarA) return
    setAplicando(elementoId)
    try {
      await api.planos.elementos.aplicar(elementoId, aplicarA.partidaId)
      await cargarElementos()
      onAplicado?.()
      notificar('Medida enviada a la partida')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setAplicando(null)
    }
  }

  async function alTerminar(tipo: Herramienta, puntos: PuntoPlano[]) {
    if (!hoja) return
    // Calibrar y anotar piden un dato más antes de poder guardarse; el resto
    // se guarda directamente.
    if (tipo === 'calibrar') {
      if (cotaPrefijada) {
        const valor = cotaPrefijada
        setCotaPrefijada(null)
        await calibrar(puntos, valor)
        return
      }
      setPendiente({ tipo, puntos })
      return
    }
    // Una nota y una línea auxiliar son lo que se pone para explicar algo, no
    // para medirlo: por eso las dos piden texto y color antes de guardarse.
    if (tipo === 'nota' || tipo === 'auxiliar') {
      setPendiente({ tipo, puntos })
      return
    }
    await guardar(tipo, puntos, null)
  }

  async function guardar(
    tipo: Herramienta,
    puntos: PuntoPlano[],
    texto: string | null,
    color?: string | null,
  ) {
    if (!hoja) return
    try {
      const creado = await api.planos.elementos.create(hoja.id, {
        tipo: tipo as ElementoPlano['tipo'],
        geometria: puntos,
        capa_id: capaActiva,
        texto,
        color: color ?? undefined,
      })
      await cargarElementos()
      if (
        autoAplicar &&
        aplicarA &&
        ['longitud', 'area', 'conteo'].includes(creado.tipo) &&
        unidadesCompatibles(creado.tipo, aplicarA.unidad)
      ) {
        await aplicar(creado.id)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function calibrar(puntos: PuntoPlano[], distancia: string) {
    if (!hoja) return
    try {
      await api.planos.calibrar(hoja.id, puntos[0], puntos[1], distancia)
      await cargar()
      await cargarElementos()
      notificar('Hoja calibrada. Se han recalculado las mediciones que había.')
      setHerramienta('mano')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  /** La revisión de verdad: además de leer, calibra si el plano lleva su
   *  escala escrita y deja señalado lo que reconoce. Lo señalado nace marcado
   *  como propuesta, así que se ve, se ajusta y no cuenta como medido hasta
   *  que alguien lo lleva a una partida a mano. */
  async function revisar(peticion?: string) {
    if (!hoja) return
    setLeyendo(true)
    setError(null)
    try {
      const revision = await api.planos.revisarConIa(hoja.id, { peticion })
      setLectura(revision)
      if (revision.calibrada || revision.elementos_creados > 0) {
        await cargar()
        await cargarElementos()
      }
      const partes: string[] = []
      if (revision.calibrada) partes.push('hoja calibrada con su escala impresa')
      if (revision.elementos_creados > 0) {
        partes.push(
          revision.elementos_creados === 1
            ? '1 elemento señalado'
            : `${revision.elementos_creados} elementos señalados`,
        )
      }
      if (partes.length > 0) notificar(partes.join(' · '))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLeyendo(false)
    }
  }

  useEffect(() => {
    if (!autoRevisarIa || !hoja || esVectorial) return
    void revisar()
    onRevisado?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRevisarIa, hoja, esVectorial])

  async function calibrarPorEscala(denominador: number) {
    if (!hoja) return
    try {
      await api.planos.calibrarPorEscala(hoja.id, denominador)
      setLectura(null)
      await cargar()
      await cargarElementos()
      notificar(`Calibrado a 1:${denominador}. Escala exacta, sin estimar nada.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function borrarHoja() {
    if (!plano || !hoja) return
    const medidas = elementos.filter((e) => TIPOS_MEDIBLES.includes(e.tipo)).length
    const aviso =
      medidas > 0
        ? `\n\nSe borrará también lo dibujado en ella (${medidas} ${
            medidas === 1 ? 'medición' : 'mediciones'
          }). Lo que ya se llevó a una partida sigue contando en el presupuesto.`
        : ''
    if (!window.confirm(`¿Quitar la hoja ${hoja.numero} de ${plano.codigo}?${aviso}`)) return
    try {
      await api.planos.hojas.remove(hoja.id)
      // Se relee el plano y se salta a la primera que quede: dejar puesto el
      // id de la hoja borrada dejaría el visor en blanco.
      const detalle = await api.planos.get(plano.id)
      setPlano(detalle)
      setHojaId(detalle.hojas[0]?.id ?? null)
      setSeleccionado(null)
      notificar('Hoja borrada')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  /** Cambia el texto o el color de algo ya dibujado. Se remanda la geometría
   *  tal cual porque el endpoint pide el elemento entero; lo que cambia aquí
   *  es solo la etiqueta y el color. */
  async function guardarElemento(
    elemento: ElementoPlano,
    cambios: { texto: string | null; color: string | null },
  ) {
    try {
      await api.planos.elementos.update(elemento.id, {
        tipo: elemento.tipo,
        geometria: elemento.geometria,
        capa_id: elemento.capa_id,
        texto: cambios.texto,
        color: cambios.color ?? undefined,
      })
      await cargarElementos()
      notificar('Elemento actualizado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function borrar(elementoId: string) {
    try {
      await api.planos.elementos.remove(elementoId)
      setSeleccionado(null)
      await cargarElementos()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  if (!plano || !hoja) {
    return (
      <>
        <ErrorNotice error={error} />
        {!error && <p className="muted">Cargando…</p>}
      </>
    )
  }

  const mediciones = elementos.filter((e) => TIPOS_MEDIBLES.includes(e.tipo))
  // Las notas y las auxiliares no miden, pero están dibujadas: sin listarlas
  // aquí, la única forma de tocarlas era acertarles con el ratón encima del
  // plano, y las que quedaban fuera de la vista no había manera de borrarlas.
  const anotaciones = elementos.filter((e) => !TIPOS_MEDIBLES.includes(e.tipo))

  const colorDe = (elemento: ElementoPlano) =>
    elemento.color ?? plano?.capas.find((c) => c.id === elemento.capa_id)?.color ?? '#b45309'

  return (
    <>
      <ErrorNotice error={error} />

      <div className="plano">
        <div className="plano__barra">
          {HERRAMIENTAS.filter((h) => !h.soloDxf || esVectorial).map(({ id: hid, etiqueta, icono: Icono }) => (
            <button
              key={hid}
              type="button"
              title={etiqueta}
              aria-label={etiqueta}
              aria-pressed={herramienta === hid}
              className={`btn btn--sm${herramienta === hid ? ' btn--primary' : ''}`}
              // Sin escala no hay medición posible: ofrecer las herramientas
              // de medir antes de calibrar solo produce elementos sin valor.
              disabled={!calibrada && ['longitud', 'area', 'entidad'].includes(hid)}
              onClick={() => setHerramienta(hid)}
            >
              <Icono size={14} aria-hidden="true" />
            </button>
          ))}

          <span className="plano__separador" />

          {plano.hojas.length > 1 && (
            <>
              <select
                className="select"
                style={{ width: 'auto' }}
                value={hoja.id}
                onChange={(e) => {
                  setHojaId(e.target.value)
                  setSeleccionado(null)
                }}
              >
                {plano.hojas.map((h) => (
                  <option key={h.id} value={h.id}>
                    Hoja {h.numero}
                    {h.metros_por_unidad == null ? ' (sin calibrar)' : ''}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn btn--sm btn--danger btn--solo-icono"
                aria-label={`Quitar la hoja ${hoja.numero}`}
                title={`Quitar la hoja ${hoja.numero} del plano`}
                onClick={() => void borrarHoja()}
              >
                <Trash2 size={14} aria-hidden="true" />
              </button>
            </>
          )}

          {!esVectorial && (
            <button
              type="button"
              className="btn btn--sm"
              disabled={leyendo}
              onClick={() => void revisar()}
            >
              <Sparkles size={14} aria-hidden="true" />{' '}
              {leyendo ? 'Revisando…' : 'Revisar con IA'}
            </button>
          )}

          <button
            type="button"
            className="btn btn--sm"
            aria-label="Alejar"
            onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}
          >
            <ZoomOut size={14} aria-hidden="true" />
          </button>
          <span className="muted">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            className="btn btn--sm"
            aria-label="Ampliar"
            onClick={() => setZoom((z) => Math.min(8, z + 0.25))}
          >
            <ZoomIn size={14} aria-hidden="true" />
          </button>

          {aplicarA && (
            <label
              className="checkbox"
              title="Cada medida nueva compatible con la unidad de esta partida se aplica sola, sin pulsar nada"
            >
              <input
                type="checkbox"
                checked={autoAplicar}
                onChange={(e) => setAutoAplicar(e.target.checked)}
              />
              <span>Aplicar automáticamente</span>
            </label>
          )}
        </div>

        {!calibrada && herramienta !== 'calibrar' && (
          <div className="plano__calibrar">
            <div>
              <strong>Esta hoja todavía no mide.</strong> Un plano es un dibujo hasta que se le
              dice una vez cuánto mide algo de él; a partir de ahí ya sale todo lo demás en
              metros. Hay dos formas:
            </div>
            <div className="plano__calibrar-opciones">
              <button
                type="button"
                className="btn btn--sm btn--primary"
                onClick={() => setHerramienta('calibrar')}
              >
                <Ruler size={14} aria-hidden="true" />
                Calibrar con una cota
              </button>
              <span className="muted">
                Pinchas los dos extremos de algo que sepas cuánto mide —una cota escrita, el
                ancho de una puerta— y escribes su medida real.
              </span>
              {!esVectorial && (
                <>
                  <button
                    type="button"
                    className="btn btn--sm"
                    disabled={leyendo}
                    onClick={() => void revisar()}
                  >
                    <Sparkles size={14} aria-hidden="true" />
                    {leyendo ? 'Revisando…' : 'Que la lea la IA'}
                  </button>
                  <span className="muted">
                    Si el plano lleva su escala escrita («E 1:50»), la lee y calibra sola. Es
                    exacto: sale de la geometría del papel, sin estimar nada.
                  </span>
                </>
              )}
            </div>
          </div>
        )}

        <p className="plano__ayuda">
          {herramienta === 'calibrar' ? (
            <strong>
              {cotaPrefijada
                ? `Cota cargada: ${cotaPrefijada} m. `
                : ''}
              {puntosEnCurso === 0
                ? 'Paso 1 de 2: pincha un extremo de algo cuya medida real conozcas.'
                : 'Paso 2 de 2: pincha el otro extremo.'}
              {cotaPrefijada ? ' Al segundo clic se calibra sola.' : ' Después te preguntará cuánto mide.'}
            </strong>
          ) : (
            AYUDA[herramienta]
          )}
        </p>

        {!esVectorial && (
          <div className="rejilla-barra">
            <Sparkles size={14} aria-hidden="true" />
            <input
              className="input"
              style={{ flex: 1, minWidth: 220 }}
              placeholder="Pídele algo a la IA: «marca las estancias», «cuenta las puertas»…"
              value={peticionIa}
              disabled={leyendo}
              onChange={(e) => setPeticionIa(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== 'Enter' || !peticionIa.trim()) return
                e.preventDefault()
                const texto = peticionIa
                setPeticionIa('')
                void revisar(texto)
              }}
            />
            <button
              type="button"
              className="btn btn--sm btn--primary"
              disabled={leyendo || !peticionIa.trim()}
              onClick={() => {
                const texto = peticionIa
                setPeticionIa('')
                void revisar(texto)
              }}
            >
              <Send size={14} aria-hidden="true" />
              {leyendo ? 'Pensando…' : 'Pedir'}
            </button>
          </div>
        )}

        <div className="plano__cuerpo">
          <div className="plano__visor" ref={visorRef}>
            <LienzoPlano
              onProgreso={setPuntosEnCurso}
              rutaArchivo={api.planos.rutaArchivo(plano.id)}
              esPdf={plano.origen === 'pdf'}
              esVectorial={esVectorial}
              hoja={hoja}
              capas={plano.capas}
              elementos={elementos}
              herramienta={herramienta}
              zoom={zoom}
              seleccionado={seleccionado}
              onSeleccionar={setSeleccionado}
              onTerminar={(t, p) => void alTerminar(t, p)}
              onEntidad={(puntos, cerrado) =>
                void guardar(cerrado ? 'area' : 'longitud', puntos, 'Entidad del plano')
              }
            />
          </div>

          <aside className="plano__panel">
            <Capas
              plano={plano}
              activa={capaActiva}
              elementos={elementos}
              onActiva={setCapaActiva}
              onCambio={cargar}
              onError={setError}
            />

            <section className="form-section">
              <h2 className="form-section__title">
                <Layers size={14} aria-hidden="true" /> Mediciones
              </h2>
              {mediciones.length === 0 ? (
                <p className="muted">Nada medido todavía en esta hoja.</p>
              ) : (
                <ul className="plano__mediciones">
                  {mediciones.map((m) => {
                    const compatible = aplicarA ? unidadesCompatibles(m.tipo, aplicarA.unidad) : false
                    const enEstaPartida =
                      aplicarA && m.linea_medicion_id
                        ? aplicarA.idsLineas.has(m.linea_medicion_id)
                        : false
                    return (
                      <li
                        key={m.id}
                        className={
                          m.id === seleccionado
                            ? 'plano__medicion is-activa'
                            : 'plano__medicion'
                        }
                      >
                        <button
                          type="button"
                          className="plano__medicion-nombre"
                          onClick={() => setSeleccionado(m.id)}
                        >
                          <span
                            className="plano__punto-color"
                            style={{ background: colorDe(m) }}
                            aria-hidden="true"
                          />
                          <span className="plano__medicion-texto">
                            {m.texto || NOMBRE_TIPO[m.tipo]}
                          </span>
                          <span className="plano__medicion-valor">
                            {m.valor == null
                              ? 'sin calibrar'
                              : `${formatoImporte(m.valor, m.tipo === 'conteo' ? 0 : 2)} ${m.unidad}`}
                          </span>
                        </button>

                        <div className="plano__medicion-pie">
                          {m.propuesto_ia && (
                            <span
                              className="badge badge--info"
                              title="Lo ha señalado la IA mirando el plano: repásalo y ajústalo antes de darlo por medido"
                            >
                              <Sparkles size={11} aria-hidden="true" /> propuesta
                            </span>
                          )}
                          {!aplicarA && m.linea_medicion_id && (
                            <span className="badge">en presupuesto</span>
                          )}
                          {enEstaPartida && (
                            <span className="badge badge--success">en esta partida</span>
                          )}
                          {aplicarA && m.linea_medicion_id && !enEstaPartida && (
                            <span className="badge">en otra partida</span>
                          )}
                          {aplicarA && !m.linea_medicion_id && m.valor != null && compatible && (
                            <button
                              type="button"
                              className="btn btn--sm"
                              disabled={aplicando === m.id}
                              onClick={() => void aplicar(m.id)}
                            >
                              <Send size={12} aria-hidden="true" />
                              {aplicando === m.id ? 'Aplicando…' : 'A la partida'}
                            </button>
                          )}
                          {aplicarA && !m.linea_medicion_id && m.valor != null && !compatible && (
                            <span className="muted" title={`Esta partida está en ${aplicarA.unidad}`}>
                              no encaja con {aplicarA.unidad}
                            </span>
                          )}
                          {m.id === seleccionado && (
                            <button
                              type="button"
                              className="btn btn--sm btn--danger btn--solo-icono"
                              aria-label="Borrar esta medición"
                              title="Borrar esta medición"
                              onClick={() => void borrar(m.id)}
                            >
                              <Trash2 size={13} aria-hidden="true" />
                            </button>
                          )}
                        </div>
                      </li>
                    )
                  })}
                </ul>
              )}
            </section>

            {anotaciones.length > 0 && (
              <section className="form-section">
                <h2 className="form-section__title">
                  <StickyNote size={14} aria-hidden="true" /> Notas y auxiliares
                </h2>
                <ul className="plano__mediciones">
                  {anotaciones.map((a) => (
                    <li
                      key={a.id}
                      className={
                        a.id === seleccionado ? 'plano__medicion is-activa' : 'plano__medicion'
                      }
                    >
                      <button
                        type="button"
                        className="plano__medicion-nombre"
                        onClick={() => setSeleccionado(a.id)}
                      >
                        <span
                          className="plano__punto-color"
                          style={{ background: colorDe(a) }}
                          aria-hidden="true"
                        />
                        <span className="plano__medicion-texto">
                          {a.texto || NOMBRE_TIPO[a.tipo]}
                        </span>
                        <span className="muted">{a.tipo === 'nota' ? 'nota' : 'auxiliar'}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {(() => {
              const elemento = elementos.find((e) => e.id === seleccionado)
              if (!elemento) return null
              return (
                <ElementoSeleccionado
                  key={elemento.id}
                  elemento={elemento}
                  colorDeCapa={
                    plano.capas.find((c) => c.id === elemento.capa_id)?.color ?? '#b45309'
                  }
                  onGuardar={(cambios) => void guardarElemento(elemento, cambios)}
                  onBorrar={() => void borrar(elemento.id)}
                />
              )
            })()}
          </aside>
        </div>
      </div>

      {pendiente?.tipo === 'calibrar' && (
        <PedirCota
          onCerrar={() => setPendiente(null)}
          onAceptar={(d) => {
            const puntos = pendiente.puntos
            setPendiente(null)
            void calibrar(puntos, d)
          }}
        />
      )}
      {lectura && (
        <LecturaIa
          lectura={lectura}
          onCerrar={() => setLectura(null)}
          onEscala={(d) => void calibrarPorEscala(d)}
          onCota={(metros) => {
            setCotaPrefijada(metros)
            setHerramienta('calibrar')
            setLectura(null)
          }}
        />
      )}
      {(pendiente?.tipo === 'nota' || pendiente?.tipo === 'auxiliar') && (
        <PedirTextoYColor
          tipo={pendiente.tipo}
          colorInicial={plano.capas.find((c) => c.id === capaActiva)?.color ?? '#b45309'}
          onCerrar={() => setPendiente(null)}
          onAceptar={(texto, color) => {
            const { tipo, puntos } = pendiente
            setPendiente(null)
            void guardar(tipo, puntos, texto, color)
          }}
        />
      )}
    </>
  )
}

function Capas({
  plano,
  activa,
  elementos,
  onActiva,
  onCambio,
  onError,
}: {
  plano: Detalle
  activa: string | null
  /** Lo dibujado en la hoja que se está viendo, para poder decir cuánto hay
   *  en cada capa. Sin ese número, apagar una capa vacía parece que no
   *  funciona cuando lo que pasa es que no había nada dentro. */
  elementos: ElementoPlano[]
  onActiva: (id: string) => void
  onCambio: () => Promise<void>
  onError: (m: string) => void
}) {
  const [nueva, setNueva] = useState('')

  const cuantosEn = useMemo(() => {
    const cuenta = new Map<string, number>()
    for (const elemento of elementos) {
      if (elemento.capa_id) cuenta.set(elemento.capa_id, (cuenta.get(elemento.capa_id) ?? 0) + 1)
    }
    return cuenta
  }, [elementos])

  async function cambiar(capa: CapaPlano, cambios: Partial<CapaPlano>) {
    try {
      // Campo a campo y no `{...capa}`: la capa que llega tiene `id`, y el
      // backend rechaza lo que no espera (`extra="forbid"`), así que mandarla
      // entera devolvía un 422 y apagar una capa no hacía nada.
      await api.planos.capas.update(capa.id, {
        nombre: capa.nombre,
        color: capa.color,
        visible: capa.visible,
        bloqueada: capa.bloqueada,
        orden: capa.orden,
        ...cambios,
      })
      await onCambio()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function borrarCapa(capa: CapaPlano) {
    const cuantos = cuantosEn.get(capa.id) ?? 0
    const aviso =
      cuantos > 0
        ? `\n\nLo dibujado en ella NO se borra: ${cuantos} ${
            cuantos === 1 ? 'elemento se queda' : 'elementos se quedan'
          } sin capa, a la vista y con su propio color.`
        : ''
    if (!window.confirm(`¿Borrar la capa «${capa.nombre}»?${aviso}`)) return
    try {
      await api.planos.capas.remove(capa.id)
      await onCambio()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  /** Sube o baja una capa y guarda el orden entero. El orden es el orden en
   *  Z: la última de la lista se pinta encima de todas. */
  async function mover(indice: number, direccion: -1 | 1) {
    const destino = indice + direccion
    if (destino < 0 || destino >= plano.capas.length) return
    const ids = plano.capas.map((c) => c.id)
    ;[ids[indice], ids[destino]] = [ids[destino], ids[indice]]
    try {
      await api.planos.capas.ordenar(plano.id, ids)
      await onCambio()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function crear() {
    if (!nueva.trim()) return
    try {
      await api.planos.capas.create(plano.id, { nombre: nueva, orden: plano.capas.length })
      setNueva('')
      await onCambio()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <section className="form-section">
      <h2 className="form-section__title">
        <Layers size={14} aria-hidden="true" /> Capas
      </h2>
      <p className="form-section__note">
        La casilla enseña o esconde lo dibujado en la capa; el nombre elige en cuál se dibuja.
        Las de abajo se pintan encima de las de arriba. El plano de fondo no está en ninguna
        capa: apagarlas todas deja el plano solo, sin lo medido encima.
      </p>
      <ul className="plano__capas">
        {plano.capas.map((capa, indice) => {
          const cuantos = cuantosEn.get(capa.id) ?? 0
          return (
          <li key={capa.id} className="plano__capa">
            <input
              type="checkbox"
              checked={capa.visible}
              aria-label={`Ver ${capa.nombre}`}
              disabled={cuantos === 0}
              title={
                cuantos === 0
                  ? 'No hay nada dibujado en esta capa en esta hoja'
                  : `Enseñar u ocultar ${cuantos} ${cuantos === 1 ? 'elemento' : 'elementos'}`
              }
              onChange={(e) => void cambiar(capa, { visible: e.target.checked })}
            />
            <input
              type="color"
              value={capa.color}
              aria-label={`Color de ${capa.nombre}`}
              onChange={(e) => void cambiar(capa, { color: e.target.value })}
            />
            <button
              type="button"
              className={
                capa.id === activa ? 'plano__capa-nombre is-activa' : 'plano__capa-nombre'
              }
              title={
                capa.id === activa
                  ? `${capa.nombre} — es donde se está dibujando`
                  : `Dibujar en ${capa.nombre}`
              }
              onClick={() => onActiva(capa.id)}
            >
              {capa.nombre}
            </button>
            <span
              className={cuantos === 0 ? 'plano__capa-cuenta is-vacia' : 'plano__capa-cuenta'}
              title={
                cuantos === 0
                  ? 'Vacía en esta hoja'
                  : `${cuantos} ${cuantos === 1 ? 'elemento' : 'elementos'} en esta hoja`
              }
            >
              {cuantos === 0 ? 'vacía' : cuantos}
            </span>
            <span className="plano__capa-orden">
              <button
                type="button"
                aria-label={`Subir ${capa.nombre}`}
                title="Subir: se pintará por debajo"
                disabled={indice === 0}
                onClick={() => void mover(indice, -1)}
              >
                <ChevronUp size={13} aria-hidden="true" />
              </button>
              <button
                type="button"
                aria-label={`Bajar ${capa.nombre}`}
                title="Bajar: se pintará por encima"
                disabled={indice === plano.capas.length - 1}
                onClick={() => void mover(indice, 1)}
              >
                <ChevronDown size={13} aria-hidden="true" />
              </button>
            </span>
            <button
              type="button"
              className="plano__capa-borrar"
              aria-label={`Borrar la capa ${capa.nombre}`}
              title="Borrar la capa (lo dibujado en ella se queda)"
              onClick={() => void borrarCapa(capa)}
            >
              <Trash2 size={13} aria-hidden="true" />
            </button>
          </li>
          )
        })}
      </ul>
      <div className="plano__capa-nueva">
        <input
          className="input input--sm"
          value={nueva}
          placeholder="Nueva capa"
          onChange={(e) => setNueva(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void crear()}
        />
        <button
          type="button"
          className="btn btn--sm btn--solo-icono"
          aria-label="Crear capa"
          onClick={() => void crear()}
        >
          <Plus size={14} aria-hidden="true" />
        </button>
      </div>
    </section>
  )
}

function PedirCota({
  onCerrar,
  onAceptar,
}: {
  onCerrar: () => void
  onAceptar: (distancia: string) => void
}) {
  const [valor, setValor] = useState('')
  const numero = Number(valor.replace(',', '.'))
  const valido = Number.isFinite(numero) && numero > 0

  return (
    <Modal title="¿Cuánto mide esa cota?" onClose={onCerrar}>
      <p className="muted">
        En metros. De aquí sale la escala de toda la hoja, así que conviene pinchar una
        cota larga: cuanto más corta, más se nota el error de un par de píxeles.
      </p>
      <Field label="Distancia real (m)">
        <input
          className="input"
          value={valor}
          autoFocus
          placeholder="Por ejemplo: 5,40"
          onChange={(e) => setValor(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && valido && onAceptar(String(numero))}
        />
      </Field>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!valido}
          onClick={() => onAceptar(String(numero))}
        >
          Calibrar
        </button>
      </div>
    </Modal>
  )
}

/** Lo dibujado que está seleccionado: su texto, su color y el botón de
 *  quitarlo. Vale para todo —una nota, una auxiliar o una medición—, porque
 *  una medición también quiere llamarse «Salón» y no «Superficie». */
function ElementoSeleccionado({
  elemento,
  colorDeCapa,
  onGuardar,
  onBorrar,
}: {
  elemento: ElementoPlano
  colorDeCapa: string
  onGuardar: (cambios: { texto: string | null; color: string | null }) => void
  onBorrar: () => void
}) {
  const [texto, setTexto] = useState(elemento.texto ?? '')
  const [color, setColor] = useState(elemento.color ?? colorDeCapa)
  const [propio, setPropio] = useState(elemento.color !== null)

  const cambiado =
    (texto.trim() || null) !== elemento.texto || (propio ? color : null) !== elemento.color

  return (
    <section className="form-section">
      <h2 className="form-section__title">{NOMBRE_TIPO[elemento.tipo]} seleccionada</h2>
      <Field label="Texto">
        <input
          className="input input--sm"
          value={texto}
          placeholder="Cómo se llama"
          onChange={(e) => setTexto(e.target.value)}
        />
      </Field>
      <Field label="Color">
        <div style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
          <input
            type="color"
            value={color}
            aria-label="Color"
            onChange={(e) => {
              setColor(e.target.value)
              setPropio(true)
            }}
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={!propio}
              onChange={(e) => setPropio(!e.target.checked)}
            />
            <span>El de la capa</span>
          </label>
        </div>
      </Field>
      <div className="form-actions">
        <button type="button" className="btn btn--sm btn--danger" onClick={onBorrar}>
          <Trash2 size={14} aria-hidden="true" /> Borrar
        </button>
        <button
          type="button"
          className="btn btn--sm btn--primary"
          disabled={!cambiado}
          onClick={() => onGuardar({ texto: texto.trim() || null, color: propio ? color : null })}
        >
          Guardar
        </button>
      </div>
    </section>
  )
}

/** Lo que se pregunta al poner una nota o una línea auxiliar: qué dice y de
 *  qué color. En la nota el texto ES el elemento, así que es obligatorio; en
 *  una auxiliar es una etiqueta opcional (para qué es esa línea). El color
 *  viene propuesto del de la capa, que es el que tendría si no se toca. */
function PedirTextoYColor({
  tipo,
  colorInicial,
  onCerrar,
  onAceptar,
}: {
  tipo: 'nota' | 'auxiliar'
  colorInicial: string
  onCerrar: () => void
  onAceptar: (texto: string | null, color: string | null) => void
}) {
  const esNota = tipo === 'nota'
  const [texto, setTexto] = useState('')
  const [color, setColor] = useState(colorInicial)
  const [propio, setPropio] = useState(false)

  function aceptar() {
    if (esNota && !texto.trim()) return
    onAceptar(texto.trim() || null, propio ? color : null)
  }

  return (
    <Modal title={esNota ? 'Nota' : 'Línea auxiliar'} onClose={onCerrar}>
      <Field label={esNota ? 'Texto' : 'Texto (opcional)'}>
        <textarea
          className="input"
          rows={esNota ? 4 : 2}
          value={texto}
          autoFocus
          placeholder={esNota ? '' : 'Para qué es esta línea: «eje de fachada», «replanteo»…'}
          onChange={(e) => setTexto(e.target.value)}
        />
      </Field>
      <Field label="Color">
        <div style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
          <input
            type="color"
            value={color}
            aria-label="Color"
            onChange={(e) => {
              setColor(e.target.value)
              setPropio(true)
            }}
          />
          <label className="checkbox">
            <input
              type="checkbox"
              checked={!propio}
              onChange={(e) => setPropio(!e.target.checked)}
            />
            <span>Usar el color de la capa</span>
          </label>
        </div>
      </Field>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={esNota && !texto.trim()}
          onClick={aceptar}
        >
          Guardar
        </button>
      </div>
    </Modal>
  )
}

function LecturaIa({
  lectura,
  onCerrar,
  onEscala,
  onCota,
}: {
  lectura: LecturaIaPlano
  onCerrar: () => void
  onEscala: (denominador: number) => void
  onCota: (metros: string) => void
}) {
  return (
    <Modal title="Lo que la IA ha leído del plano" onClose={onCerrar}>
      {lectura.resumen && <p>{lectura.resumen}</p>}

      {lectura.escala_impresa !== null && lectura.escala_aplicable && (
        <section className="form-section">
          <h2 className="form-section__title">
            Escala impresa: 1:{lectura.escala_impresa}
            {lectura.escala_texto && ` («${lectura.escala_texto}»)`}
          </h2>
          <p className="muted">
            Con esto la calibración es <strong>exacta</strong>: la cuenta sale de la
            geometría del papel, no de estimar píxeles. Es la mejor opción si el
            cajetín dice la verdad y el PDF no se ha reescalado al imprimirlo.
          </p>
          <div className="form-actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => onEscala(lectura.escala_impresa!)}
            >
              Calibrar a 1:{lectura.escala_impresa}
            </button>
          </div>
        </section>
      )}

      {lectura.escala_impresa !== null && !lectura.escala_aplicable && (
        <section className="form-section">
          <h2 className="form-section__title">Escala impresa: 1:{lectura.escala_impresa}</h2>
          <p className="muted">
            No se puede aplicar en una imagen: un píxel no mide nada sin saber a qué
            resolución se escaneó. Usa una de las cotas de abajo.
          </p>
        </section>
      )}

      {lectura.cotas.length > 0 && (
        <section className="form-section">
          <h2 className="form-section__title">Cotas que ha leído</h2>
          <p className="muted">
            El valor es de fiar porque está escrito; dónde empieza y acaba, no. Elige
            una y pincha sus dos extremos.
          </p>
          <ul className="lista">
            {lectura.cotas.map((c, i) => (
              <li key={i}>
                <button type="button" className="btn-enlace" onClick={() => onCota(c.metros)}>
                  {c.texto} → {c.metros} m
                </button>
                {c.donde && <span className="muted"> · {c.donde}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {lectura.avisos.length > 0 && (
        <section className="form-section">
          <h2 className="form-section__title">Avisos</h2>
          <ul className="lista">
            {lectura.avisos.map((a, i) => (
              <li key={i} className="muted">
                {a}
              </li>
            ))}
          </ul>
        </section>
      )}

      {lectura.escala_impresa === null && lectura.cotas.length === 0 && (
        <p className="muted">
          No ha encontrado ni escala ni cotas escritas. Calíbralo a mano pinchando una
          medida que conozcas.
        </p>
      )}

      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </Modal>
  )
}
