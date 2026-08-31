import { useEffect, useRef } from 'react'

import type { CapaPlano, DibujoVectorial } from '../lib/api'

/** Ancho máximo del bitmap donde se pinta el DXF. Ampliar mucho un plano y
 *  redibujar a resolución infinita acabaría comiéndose la memoria del
 *  navegador; 4000 px ya se ve nítido en cualquier pantalla. */
const MAX_PIXELES = 4000

/** El dibujo de un DXF, en canvas y no en SVG.
 *
 *  Un plano de arquitectura trae decenas de miles de entidades. Cada una como
 *  un `<polyline>` serían decenas de miles de nodos del DOM: el navegador se
 *  arrastra al hacer zoom y al mover el plano. En canvas es una sola pasada de
 *  dibujo, y lo que hay que pinchar se resuelve con las coordenadas, que ya
 *  están en memoria (ver `trazoMasCercano`). */
export function DibujoDxf({
  dibujo,
  capas,
  ancho,
  alto,
  zoom,
  resaltado,
}: {
  dibujo: DibujoVectorial
  capas: CapaPlano[]
  ancho: number
  alto: number
  zoom: number
  /** Índice del trazo bajo el cursor o recién elegido. */
  resaltado: number | null
}) {
  const lienzoRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = lienzoRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const escala = Math.min((MAX_PIXELES / ancho) * Math.min(zoom, 4), MAX_PIXELES / ancho)
    canvas.width = Math.max(1, Math.floor(ancho * escala))
    canvas.height = Math.max(1, Math.floor(alto * escala))

    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.lineJoin = 'round'
    ctx.lineCap = 'round'

    // El grosor va en píxeles del bitmap, y el bitmap se muestra reducido:
    // aquí se dibuja a 4000 px de ancho lo que en pantalla ocupa 850. Con
    // `lineWidth = 1` la línea acaba midiendo 0,2 px en pantalla y el plano se
    // ve desvanecido, a trocitos. Atarlo a la razón entre ambos tamaños es lo
    // que hace que un trazo mida siempre un píxel de los de ver.
    const razon = canvas.clientWidth > 0 ? canvas.width / canvas.clientWidth : 2
    const grosor = Math.max(1, razon)

    // Las capas del DXF se crearon con su mismo nombre al importarlo, así que
    // el color y el interruptor de visibilidad salen de ahí.
    const porNombre = new Map(capas.map((c) => [c.nombre, c]))

    dibujo.trazos.forEach((trazo, indice) => {
      const capa = porNombre.get(trazo.c)
      if (capa && !capa.visible) return
      ctx.strokeStyle = indice === resaltado ? '#b45309' : capa?.color ?? '#333333'
      ctx.lineWidth = indice === resaltado ? grosor * 3 : grosor

      const puntos = trazo.p
      if (puntos.length === 1) {
        // Un POINT del DXF: sin esto, los puntos sueltos (arquetas, luminarias)
        // no se verían y son justo lo que se cuenta.
        // El `fillStyle` sigue siendo el blanco del fondo si no se cambia
        // aquí: los puntos existirían y no se verían.
        ctx.fillStyle = ctx.strokeStyle
        ctx.beginPath()
        ctx.arc(puntos[0][0] * escala, puntos[0][1] * escala, grosor * 2, 0, Math.PI * 2)
        ctx.fill()
        return
      }
      ctx.beginPath()
      ctx.moveTo(puntos[0][0] * escala, puntos[0][1] * escala)
      for (let i = 1; i < puntos.length; i++) {
        ctx.lineTo(puntos[i][0] * escala, puntos[i][1] * escala)
      }
      if (trazo.z) ctx.closePath()
      ctx.stroke()
    })
  }, [dibujo, capas, ancho, alto, zoom, resaltado])

  return <canvas ref={lienzoRef} className="lienzo__fondo" />
}

/** El trazo más cercano a un punto, o `null` si no hay ninguno lo bastante
 *  cerca. Sin la tolerancia, cualquier clic en medio de la nada elegiría la
 *  entidad más próxima aunque estuviera a media hoja. */
export function trazoMasCercano(
  dibujo: DibujoVectorial,
  capas: CapaPlano[],
  x: number,
  y: number,
  tolerancia: number,
): number | null {
  const porNombre = new Map(capas.map((c) => [c.nombre, c]))
  let mejor: number | null = null
  let mejorDistancia = tolerancia

  dibujo.trazos.forEach((trazo, indice) => {
    const capa = porNombre.get(trazo.c)
    // Una capa apagada no se puede pinchar: si no, se mediría algo que no se
    // está viendo.
    if (capa && !capa.visible) return
    const puntos = trazo.p
    for (let i = 0; i < puntos.length; i++) {
      const a = puntos[i]
      const b = i + 1 < puntos.length ? puntos[i + 1] : trazo.z ? puntos[0] : null
      const d = b ? distanciaASegmento(x, y, a[0], a[1], b[0], b[1]) : Math.hypot(x - a[0], y - a[1])
      if (d < mejorDistancia) {
        mejorDistancia = d
        mejor = indice
      }
    }
  })
  return mejor
}

function distanciaASegmento(
  px: number,
  py: number,
  ax: number,
  ay: number,
  bx: number,
  by: number,
): number {
  const dx = bx - ax
  const dy = by - ay
  const largo = dx * dx + dy * dy
  if (largo === 0) return Math.hypot(px - ax, py - ay)
  // Proyección acotada al segmento: sin el `max/min`, una pared corta
  // "atraería" clics que caen en su prolongación, muy lejos de ella.
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / largo))
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy))
}
