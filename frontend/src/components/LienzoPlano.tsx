import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { PDFDocumentProxy } from 'pdfjs-dist'

import { DibujoDxf, trazoMasCercano } from './DibujoDxf'
import { traerBlob } from '../lib/api'
import { pdfjs } from '../lib/pdfjs'
import type { CapaPlano, ElementoPlano, HojaPlano, PuntoPlano } from '../lib/api'

/** Lo mínimo de una tarea de render de pdf.js, sin arrastrar su tipo interno
 *  (cambia de nombre entre versiones). Mismo criterio que en `VistaPdf`. */
type TareaRender = { promise: Promise<unknown>; cancel: () => void }

export type Herramienta =
  | 'mano'
  | 'entidad'
  | 'calibrar'
  | 'longitud'
  | 'area'
  | 'conteo'
  | 'nota'
  | 'auxiliar'

/** Cuántos puntos necesita cada herramienta antes de poder cerrarse. Las que
 *  valen `null` son de longitud libre: se cierran a mano. */
const PUNTOS_EXACTOS: Record<Herramienta, number | null> = {
  mano: 0,
  // No dibuja: elige una entidad del DXF y la mide entera.
  entidad: 0,
  calibrar: 2,
  longitud: null,
  area: null,
  conteo: null,
  nota: 1,
  auxiliar: 2,
}

const COLOR_POR_DEFECTO = '#b45309'

/** El plano y todo lo que se dibuja encima.
 *
 *  El fondo se pinta en un `<canvas>` (pdf.js) o en un `<img>`, y el dibujo va
 *  en un `<svg>` superpuesto **con el viewBox en coordenadas de hoja**. Eso es
 *  lo que hace que no haya conversiones de coordenadas por ninguna parte: el
 *  navegador escala el SVG solo, y un punto guardado en la base se pinta igual
 *  con cualquier zoom y en cualquier ventana. */
export function LienzoPlano({
  rutaArchivo,
  esPdf,
  esVectorial,
  hoja,
  capas,
  elementos,
  herramienta,
  zoom,
  seleccionado,
  onSeleccionar,
  onTerminar,
  onEntidad,
  onProgreso,
}: {
  rutaArchivo: string
  esPdf: boolean
  esVectorial: boolean
  hoja: HojaPlano
  capas: CapaPlano[]
  elementos: ElementoPlano[]
  herramienta: Herramienta
  zoom: number
  seleccionado: string | null
  onSeleccionar: (id: string | null) => void
  /** Un trazo terminado. El componente no guarda nada: solo dibuja y avisa. */
  onTerminar: (tipo: Herramienta, puntos: PuntoPlano[]) => void
  /** Una entidad del DXF elegida para medirla entera, con su geometría
   *  exacta: aquí no se estima nada. */
  onEntidad?: (puntos: PuntoPlano[], cerrado: boolean) => void
  /** Cuántos puntos lleva puestos el trazo a medias. Sirve para poder guiar
   *  paso a paso desde fuera («pincha el otro extremo»), que es la diferencia
   *  entre una herramienta que se entiende y una que hay que adivinar. */
  onProgreso?: (puntos: number) => void
}) {
  const ancho = Number(hoja.ancho)
  const alto = Number(hoja.alto)
  const [enCurso, setEnCurso] = useState<PuntoPlano[]>([])
  const [trazoBajoCursor, setTrazoBajoCursor] = useState<number | null>(null)
  const [raton, setRaton] = useState<PuntoPlano | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  // Cambiar de hoja o de herramienta descarta el trazo a medias. Arrastrarlo
  // de una hoja a otra pintaría una medición sobre un plano distinto.
  useEffect(() => {
    setEnCurso([])
  }, [hoja.id, herramienta])

  useEffect(() => {
    onProgreso?.(enCurso.length)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enCurso.length])

  const colorDeCapa = useMemo(() => {
    const mapa = new Map(capas.map((c) => [c.id, c]))
    return (id: string | null) => (id ? mapa.get(id) ?? null : null)
  }, [capas])

  const visibles = useMemo(() => {
    const dentro = elementos.filter((e) => {
      const capa = colorDeCapa(e.capa_id)
      return capa ? capa.visible : true
    })
    // El orden de las capas es el orden en Z. Lo que no tiene capa se pinta
    // al final —encima de todo— y no debajo: son elementos viejos o de una
    // capa borrada, y esconderlos bajo las demás sería perderlos de vista sin
    // que nada lo explique.
    return dentro
      .map((elemento, i) => ({ elemento, i, orden: colorDeCapa(elemento.capa_id)?.orden }))
      .sort((a, b) => (a.orden ?? Infinity) - (b.orden ?? Infinity) || a.i - b.i)
      .map((x) => x.elemento)
  }, [elementos, colorDeCapa])

  function puntoDelEvento(evento: React.MouseEvent): PuntoPlano | null {
    const svg = svgRef.current
    if (!svg) return null
    const caja = svg.getBoundingClientRect()
    if (!caja.width || !caja.height) return null
    return {
      x: ((evento.clientX - caja.left) / caja.width) * ancho,
      y: ((evento.clientY - caja.top) / caja.height) * alto,
    }
  }

  function alPinchar(evento: React.MouseEvent) {
    if (herramienta === 'mano') {
      onSeleccionar(null)
      return
    }
    const punto = puntoDelEvento(evento)
    if (!punto) return

    if (herramienta === 'entidad') {
      const dibujo = hoja.dibujo
      if (!dibujo || !onEntidad) return
      const indice = trazoMasCercano(dibujo, capas, punto.x, punto.y, ancho / 150)
      if (indice === null) return
      const trazo = dibujo.trazos[indice]
      onEntidad(
        trazo.p.map(([x, y]) => ({ x, y })),
        Boolean(trazo.z),
      )
      return
    }

    const siguiente = [...enCurso, punto]
    const exactos = PUNTOS_EXACTOS[herramienta]
    if (exactos !== null && siguiente.length >= exactos) {
      setEnCurso([])
      onTerminar(herramienta, siguiente)
      return
    }
    setEnCurso(siguiente)
  }

  const cerrar = useCallback(() => {
    // El conteo se cierra con lo que haya (cada clic es una unidad); una
    // longitud necesita dos puntos y un área tres. Cerrar con menos crearía
    // un elemento que el servidor rechazaría, así que ni se intenta.
    const minimo = herramienta === 'area' ? 3 : herramienta === 'longitud' ? 2 : 1
    if (enCurso.length >= minimo) onTerminar(herramienta, enCurso)
    setEnCurso([])
  }, [enCurso, herramienta, onTerminar])

  useEffect(() => {
    function alTeclear(evento: KeyboardEvent) {
      if (evento.key === 'Enter') cerrar()
      if (evento.key === 'Escape') setEnCurso([])
    }
    window.addEventListener('keydown', alTeclear)
    return () => window.removeEventListener('keydown', alTeclear)
  }, [cerrar])

  // El grosor del trazo se divide por el zoom para que se vea siempre igual
  // de fino: si no, al ampliar el plano las líneas engordan y tapan justo lo
  // que se estaba intentando medir.
  const trazo = (ancho / 600) / zoom

  return (
    <div className="lienzo" style={{ width: `${zoom * 100}%` }}>
      {esVectorial && hoja.dibujo ? (
        <DibujoDxf
          dibujo={hoja.dibujo}
          capas={capas}
          ancho={ancho}
          alto={alto}
          zoom={zoom}
          resaltado={trazoBajoCursor}
        />
      ) : esPdf ? (
        <FondoPdf ruta={rutaArchivo} pagina={hoja.numero} />
      ) : (
        <FondoImagen ruta={rutaArchivo} />
      )}

      <svg
        ref={svgRef}
        className="lienzo__capa"
        viewBox={`0 0 ${ancho} ${alto}`}
        preserveAspectRatio="none"
        onClick={alPinchar}
        onDoubleClick={cerrar}
        onMouseMove={(e) => {
          if (herramienta === 'mano') return
          const punto = puntoDelEvento(e)
          setRaton(punto)
          // Con la herramienta de entidad se resalta la que se elegiría al
          // pinchar: en un plano lleno de líneas, sin esto no se sabe cuál
          // vas a medir hasta después de haberla medido.
          if (herramienta === 'entidad' && punto && hoja.dibujo) {
            setTrazoBajoCursor(
              trazoMasCercano(hoja.dibujo, capas, punto.x, punto.y, ancho / 150),
            )
          }
        }}
        onMouseLeave={() => {
          setRaton(null)
          setTrazoBajoCursor(null)
        }}
        style={{ cursor: herramienta === 'mano' ? 'default' : 'crosshair' }}
      >
        {visibles.map((elemento) => (
          <Dibujo
            key={elemento.id}
            elemento={elemento}
            color={colorDeCapa(elemento.capa_id)?.color ?? elemento.color ?? COLOR_POR_DEFECTO}
            trazo={trazo}
            resaltado={elemento.id === seleccionado}
            onPinchar={(e) => {
              e.stopPropagation()
              onSeleccionar(elemento.id)
            }}
          />
        ))}

        {enCurso.length > 0 && (
          <Provisional
            puntos={enCurso}
            raton={raton}
            herramienta={herramienta}
            trazo={trazo}
          />
        )}
      </svg>
    </div>
  )
}

function FondoImagen({ ruta }: { ruta: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let vigente: string | null = null
    void (async () => {
      try {
        vigente = URL.createObjectURL(await traerBlob(ruta))
        setUrl(vigente)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'No se pudo abrir la imagen')
      }
    })()
    return () => {
      if (vigente) URL.revokeObjectURL(vigente)
    }
  }, [ruta])

  if (error) return <div className="lienzo__error">{error}</div>
  if (!url) return <div className="lienzo__fondo" />
  return <img src={url} alt="" className="lienzo__fondo" />
}

function FondoPdf({ ruta, pagina }: { ruta: string; pagina: number }) {
  const lienzoRef = useRef<HTMLCanvasElement>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelado = false
    let tarea: TareaRender | null = null
    let documento: PDFDocumentProxy | null = null

    void (async () => {
      try {
        // El fichero se trae con la sesión puesta y se le da a pdf.js ya en
        // memoria: si se le pasa la URL, la pide él sin cabeceras y se lleva
        // un 401.
        const datos = new Uint8Array(await (await traerBlob(ruta)).arrayBuffer())
        if (cancelado) return
        documento = await pdfjs.getDocument({ data: datos }).promise
        const pag = await documento.getPage(pagina)
        const canvas = lienzoRef.current
        if (cancelado || !canvas) return

        const base = pag.getViewport({ scale: 1 })
        // Se rasteriza a una resolución fija y alta, no a la de pantalla: el
        // zoom del lienzo es CSS sobre este bitmap, y volver a rasterizar en
        // cada paso del zoom haría inusable el plano en un portátil.
        const escala = Math.min(2400 / base.width, 4)
        const vista = pag.getViewport({ scale: escala })
        canvas.width = Math.floor(vista.width)
        canvas.height = Math.floor(vista.height)
        const ctx = canvas.getContext('2d')
        if (!ctx) return
        tarea = pag.render({ canvasContext: ctx, viewport: vista }) as unknown as TareaRender
        await tarea.promise
      } catch (err) {
        // `cancel()` rechaza la promesa a propósito al desmontar: eso no es un
        // fallo que haya que enseñar.
        if (!cancelado) setError(err instanceof Error ? err.message : 'No se pudo abrir el PDF')
      }
    })()

    return () => {
      cancelado = true
      tarea?.cancel()
      void documento?.destroy()
    }
  }, [ruta, pagina])

  if (error) return <div className="lienzo__error">{error}</div>
  return <canvas ref={lienzoRef} className="lienzo__fondo" />
}

function Dibujo({
  elemento,
  color,
  trazo,
  resaltado,
  onPinchar,
}: {
  elemento: ElementoPlano
  color: string
  trazo: number
  resaltado: boolean
  onPinchar: (e: React.MouseEvent) => void
}) {
  const puntos = elemento.geometria
  const ancho = resaltado ? trazo * 2 : trazo
  const comunes = {
    onClick: onPinchar,
    style: { cursor: 'pointer' } as const,
    stroke: color,
    strokeWidth: ancho,
    // Sin esto hay que acertar sobre una línea de un píxel de grosor.
    vectorEffect: 'non-scaling-stroke' as const,
  }

  if (elemento.tipo === 'nota' || elemento.tipo === 'conteo') {
    return (
      <g>
        {puntos.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={trazo * 3} fill={color} {...comunes} />
        ))}
        {elemento.texto && puntos[0] && (
          <text
            x={puntos[0].x + trazo * 5}
            y={puntos[0].y - trazo * 3}
            fill={color}
            fontSize={trazo * 10}
            onClick={onPinchar}
          >
            {elemento.texto}
          </text>
        )}
      </g>
    )
  }

  const trayecto = puntos.map((p) => `${p.x},${p.y}`).join(' ')
  if (elemento.tipo === 'area') {
    return (
      <polygon {...comunes} points={trayecto} fill={color} fillOpacity={resaltado ? 0.3 : 0.15} />
    )
  }
  return (
    <polyline
      {...comunes}
      points={trayecto}
      fill="none"
      // La línea auxiliar va a trazos: sirve para alinear, no mide, y tiene
      // que distinguirse de un vistazo de una medición de longitud.
      strokeDasharray={elemento.tipo === 'auxiliar' ? `${trazo * 6} ${trazo * 4}` : undefined}
    />
  )
}

function Provisional({
  puntos,
  raton,
  herramienta,
  trazo,
}: {
  puntos: PuntoPlano[]
  raton: PuntoPlano | null
  herramienta: Herramienta
  trazo: number
}) {
  const color = herramienta === 'calibrar' ? '#15803d' : COLOR_POR_DEFECTO
  const seguidos = raton ? [...puntos, raton] : puntos
  return (
    <g pointerEvents="none">
      <polyline
        points={seguidos.map((p) => `${p.x},${p.y}`).join(' ')}
        fill="none"
        stroke={color}
        strokeWidth={trazo}
        strokeDasharray={`${trazo * 4} ${trazo * 3}`}
        vectorEffect="non-scaling-stroke"
      />
      {puntos.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={trazo * 2.5} fill={color} />
      ))}
    </g>
  )
}
