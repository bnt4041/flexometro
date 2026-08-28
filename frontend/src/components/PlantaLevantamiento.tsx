import { useEffect, useRef } from 'react'

/** Un vértice del levantamiento, ya proyectado a planta: son las coordenadas
 *  `x` y `z` del punto 3D que dio el AR (en WebXR el eje `y` es la vertical,
 *  así que descartarlo ES la vista en planta). En metros. */
export interface PuntoPlanta {
  x: number
  z: number
  etiqueta?: string | null
}

function formatoCota(metros: number): string {
  return metros < 1 ? `${Math.round(metros * 100)} cm` : `${metros.toFixed(2)} m`
}

/** Área del polígono por la fórmula de la superficie gaussiana (shoelace).
 *  Sale en m² porque los puntos vienen en metros. */
export function areaDe(puntos: PuntoPlanta[]): number {
  if (puntos.length < 3) return 0
  let suma = 0
  for (let i = 0; i < puntos.length; i++) {
    const a = puntos[i]
    const b = puntos[(i + 1) % puntos.length]
    suma += a.x * b.z - b.x * a.z
  }
  return Math.abs(suma / 2)
}

export function perimetroDe(puntos: PuntoPlanta[], cerrado: boolean): number {
  let total = 0
  const tramos = cerrado ? puntos.length : puntos.length - 1
  for (let i = 0; i < tramos; i++) {
    const a = puntos[i]
    const b = puntos[(i + 1) % puntos.length]
    total += Math.hypot(b.x - a.x, b.z - a.z)
  }
  return total
}

/** La planta que se va dibujando en vivo mientras se marcan esquinas.
 *  Siempre centrada y reescalada para que quepa entera: el levantamiento
 *  crece según se camina, y el usuario no debería tener que encuadrarlo a
 *  mano mientras tiene el móvil en alto. */
export function PlantaLevantamiento({
  puntos,
  cerrado,
  posicionActual,
}: {
  puntos: PuntoPlanta[]
  cerrado: boolean
  /** Dónde apunta el retículo ahora — se pinta como tramo de puntos desde el
   *  último vértice, para ver el tramo antes de fijarlo. */
  posicionActual?: PuntoPlanta | null
}) {
  const lienzoRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = lienzoRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // El canvas se dimensiona al tamaño real en píxeles de su caja CSS, para
    // que el dibujo no salga borroso en pantallas con densidad alta.
    const caja = canvas.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    if (canvas.width !== caja.width * dpr || canvas.height !== caja.height * dpr) {
      canvas.width = caja.width * dpr
      canvas.height = caja.height * dpr
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, caja.width, caja.height)

    const todos = posicionActual ? [...puntos, posicionActual] : puntos
    if (todos.length === 0) {
      ctx.fillStyle = 'rgba(255,255,255,0.5)'
      ctx.font = '13px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('Marca la primera esquina', caja.width / 2, caja.height / 2)
      return
    }

    // Auto-encuadre: caja envolvente de todo lo dibujado + margen, escalado
    // para caber. `escala` es px por metro.
    const margen = 34
    const xs = todos.map((p) => p.x)
    const zs = todos.map((p) => p.z)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minZ = Math.min(...zs)
    const maxZ = Math.max(...zs)
    const anchoM = Math.max(maxX - minX, 0.5)
    const altoM = Math.max(maxZ - minZ, 0.5)
    const escala = Math.min((caja.width - margen * 2) / anchoM, (caja.height - margen * 2) / altoM)
    const centroX = (minX + maxX) / 2
    const centroZ = (minZ + maxZ) / 2
    const aPantalla = (p: PuntoPlanta) => ({
      x: caja.width / 2 + (p.x - centroX) * escala,
      y: caja.height / 2 + (p.z - centroZ) * escala,
    })

    // Tramos ya fijados.
    if (puntos.length >= 2) {
      ctx.beginPath()
      puntos.forEach((p, i) => {
        const s = aPantalla(p)
        if (i === 0) ctx.moveTo(s.x, s.y)
        else ctx.lineTo(s.x, s.y)
      })
      if (cerrado) ctx.closePath()
      if (cerrado) {
        ctx.fillStyle = 'rgba(245,158,11,0.18)'
        ctx.fill()
      }
      ctx.strokeStyle = '#f59e0b'
      ctx.lineWidth = 2
      ctx.stroke()
    }

    // Tramo en curso, discontinuo, hasta donde apunta el retículo.
    if (posicionActual && puntos.length >= 1) {
      const a = aPantalla(puntos[puntos.length - 1])
      const b = aPantalla(posicionActual)
      ctx.save()
      ctx.setLineDash([5, 4])
      ctx.strokeStyle = 'rgba(255,255,255,0.7)'
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.moveTo(a.x, a.y)
      ctx.lineTo(b.x, b.y)
      ctx.stroke()
      ctx.restore()
    }

    // Cotas de cada tramo, en el punto medio.
    ctx.font = 'bold 11px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const tramos = cerrado ? puntos.length : puntos.length - 1
    for (let i = 0; i < tramos; i++) {
      const a = puntos[i]
      const b = puntos[(i + 1) % puntos.length]
      const largo = Math.hypot(b.x - a.x, b.z - a.z)
      const sa = aPantalla(a)
      const sb = aPantalla(b)
      const mx = (sa.x + sb.x) / 2
      const my = (sa.y + sb.y) / 2
      const texto = formatoCota(largo)
      const w = ctx.measureText(texto).width
      ctx.fillStyle = 'rgba(0,0,0,0.75)'
      ctx.fillRect(mx - w / 2 - 4, my - 8, w + 8, 16)
      ctx.fillStyle = '#fde68a'
      ctx.fillText(texto, mx, my)
    }

    // Vértices: el último, más grande, para saber desde dónde sigue el trazo.
    puntos.forEach((p, i) => {
      const s = aPantalla(p)
      const ultimo = i === puntos.length - 1 && !cerrado
      ctx.beginPath()
      ctx.arc(s.x, s.y, ultimo ? 6 : 4, 0, Math.PI * 2)
      ctx.fillStyle = ultimo ? '#fff' : '#f59e0b'
      ctx.fill()
      if (ultimo) {
        ctx.strokeStyle = '#f59e0b'
        ctx.lineWidth = 2
        ctx.stroke()
      }
      if (p.etiqueta) {
        ctx.font = '10px sans-serif'
        ctx.fillStyle = 'rgba(255,255,255,0.85)'
        ctx.fillText(p.etiqueta, s.x, s.y - 12)
      }
    })
  }, [puntos, cerrado, posicionActual])

  return <canvas ref={lienzoRef} style={{ width: '100%', height: '100%', display: 'block' }} />
}
