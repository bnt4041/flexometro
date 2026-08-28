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

const TOLERANCIA_ANGULO_RECTO = (8 * Math.PI) / 180

function normalizarAngulo(a: number): number {
  while (a <= -Math.PI) a += 2 * Math.PI
  while (a > Math.PI) a -= 2 * Math.PI
  return a
}

/** Solo para EL DIBUJO: si el giro en una esquina ya anda cerca de 90º, lo
 *  deja en exactamente 90º — en una habitación real casi todas las esquinas
 *  SON rectas, y lo que se aleja un poco de 90º suele ser ruido del propio
 *  seguimiento AR, no la esquina real. Conserva la longitud de cada tramo
 *  (solo gira la dirección), así las cotas de cada pared no cambian —
 *  siguen calculándose de las coordenadas originales, no de este ajuste — y
 *  el m² del bloque de arriba tampoco: ese sigue siendo la medida real. Es
 *  puramente estético, tramo a tramo desde el primero (que se queda fijo
 *  como referencia): en un perímetro cerrado con más de un par de esquinas
 *  desviadas, el último tramo puede no cerrar perfecto contra el primero —
 *  aceptable para una vista rápida en obra, no para un plano de precisión. */
function esquinasARectas(puntos: PuntoPlanta[]): PuntoPlanta[] {
  if (puntos.length < 3) return puntos
  const ajustados: PuntoPlanta[] = [puntos[0]]
  let direccion = Math.atan2(puntos[1].z - puntos[0].z, puntos[1].x - puntos[0].x)
  for (let i = 1; i < puntos.length; i++) {
    const largo = Math.hypot(puntos[i].x - puntos[i - 1].x, puntos[i].z - puntos[i - 1].z)
    const anterior = ajustados[i - 1]
    ajustados.push({
      x: anterior.x + Math.cos(direccion) * largo,
      z: anterior.z + Math.sin(direccion) * largo,
      etiqueta: puntos[i].etiqueta,
    })
    if (i < puntos.length - 1) {
      const direccionSiguiente = Math.atan2(
        puntos[i + 1].z - puntos[i].z,
        puntos[i + 1].x - puntos[i].x,
      )
      const giro = normalizarAngulo(direccionSiguiente - direccion)
      const cercaDeRecto = Math.abs(Math.abs(giro) - Math.PI / 2) < TOLERANCIA_ANGULO_RECTO
      direccion += cercaDeRecto ? Math.sign(giro) * (Math.PI / 2) : giro
    }
  }
  return ajustados
}

/** Un elemento que la IA ha situado sobre un muro (ver `planta.py`). */
export interface ElementoEnMuro {
  muro: number
  tipo: string
  ancho_cm: number | null
  alto_cm: number | null
  /** Posición a lo largo del muro, como fracción de 0 a 1 de su longitud. */
  desde: number
  hasta: number
  confianza: string | null
}

/** Qué familia de símbolo dibujar. La IA devuelve el tipo en texto libre
 *  ("puerta de paso", "ventana corredera"...), así que se clasifica por lo
 *  que contenga en vez de por una lista cerrada. */
function familiaDe(tipo: string): 'puerta' | 'ventana' | 'hueco' | 'otro' {
  const t = tipo.toLowerCase()
  if (t.includes('puerta')) return 'puerta'
  if (t.includes('ventan') || t.includes('acristal')) return 'ventana'
  if (t.includes('hueco') || t.includes('paso') || t.includes('arco')) return 'hueco'
  return 'otro'
}

/** El mismo color de fondo que el panel de la planta en `TestMeter`: se usa
 *  para "abrir" el hueco de puertas y ventanas tapando el trazo del muro. */
const FONDO_PANEL = '#0c0e12'

const COLOR_ELEMENTO: Record<string, string> = {
  puerta: '#93c5fd',
  ventana: '#67e8f9',
  hueco: '#d8b4fe',
  otro: '#a3a3a3',
}

/** La planta que se va dibujando en vivo mientras se marcan esquinas.
 *  Siempre centrada y reescalada para que quepa entera: el levantamiento
 *  crece según se camina, y el usuario no debería tener que encuadrarlo a
 *  mano mientras tiene el móvil en alto. */
export function PlantaLevantamiento({
  puntos,
  cerrado,
  posicionActual,
  elementos = [],
}: {
  puntos: PuntoPlanta[]
  cerrado: boolean
  /** Dónde apunta el retículo ahora — se pinta como tramo de puntos desde el
   *  último vértice, para ver el tramo antes de fijarlo. */
  posicionActual?: PuntoPlanta | null
  /** Lo que la IA ha reconocido en las fotos, ya asignado a cada muro. Se
   *  dibuja encima de la pared correspondiente. */
  elementos?: ElementoEnMuro[]
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

    if (puntos.length === 0 && !posicionActual) {
      ctx.fillStyle = 'rgba(255,255,255,0.5)'
      ctx.font = '13px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('Marca la primera esquina', caja.width / 2, caja.height / 2)
      return
    }

    // Los puntos "rectificados" son solo para el dibujo (línea, relleno,
    // marcadores) — las cotas de texto siguen saliendo de `puntos` (más
    // abajo), sin pasar por este ajuste.
    const rectos = esquinasARectas(puntos)
    const todos = posicionActual ? [...rectos, posicionActual] : rectos

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
    if (rectos.length >= 2) {
      ctx.beginPath()
      rectos.forEach((p, i) => {
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
    if (posicionActual && rectos.length >= 1) {
      const a = aPantalla(rectos[rectos.length - 1])
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

    // Elementos que la IA ha situado en cada muro, dibujados ENCIMA de la
    // pared: primero se "abre" el hueco tapando el trazo de la pared con el
    // fondo del panel, y luego se pinta el símbolo.
    for (const el of elementos) {
      const a = rectos[el.muro]
      const b = rectos[(el.muro + 1) % rectos.length]
      if (!a || !b) continue
      const sa = aPantalla(a)
      const sb = aPantalla(b)
      const p1 = { x: sa.x + (sb.x - sa.x) * el.desde, y: sa.y + (sb.y - sa.y) * el.desde }
      const p2 = { x: sa.x + (sb.x - sa.x) * el.hasta, y: sa.y + (sb.y - sa.y) * el.hasta }
      const familia = familiaDe(el.tipo)
      const color = COLOR_ELEMENTO[familia]
      const largoPx = Math.hypot(p2.x - p1.x, p2.y - p1.y)
      if (largoPx < 1) continue
      // Normal al muro, para el arco de la puerta y el grosor de la ventana.
      const nx = -(p2.y - p1.y) / largoPx
      const ny = (p2.x - p1.x) / largoPx

      // El hueco: tapa el trazo naranja de la pared en ese tramo.
      ctx.save()
      ctx.strokeStyle = FONDO_PANEL
      ctx.lineWidth = 4
      ctx.beginPath()
      ctx.moveTo(p1.x, p1.y)
      ctx.lineTo(p2.x, p2.y)
      ctx.stroke()
      ctx.restore()

      ctx.save()
      ctx.strokeStyle = color
      ctx.fillStyle = color
      if (familia === 'puerta') {
        // Convención de plano: hoja abierta 90º + arco de barrido.
        ctx.lineWidth = 2
        ctx.beginPath()
        ctx.moveTo(p1.x, p1.y)
        ctx.lineTo(p1.x + nx * largoPx, p1.y + ny * largoPx)
        ctx.stroke()
        ctx.globalAlpha = 0.55
        ctx.lineWidth = 1
        ctx.beginPath()
        ctx.arc(
          p1.x,
          p1.y,
          largoPx,
          Math.atan2(ny, nx),
          Math.atan2(p2.y - p1.y, p2.x - p1.x),
          false,
        )
        ctx.stroke()
      } else if (familia === 'ventana') {
        // Doble línea fina, el símbolo habitual de acristalamiento.
        ctx.lineWidth = 1.5
        for (const desplazamiento of [-2, 2]) {
          ctx.beginPath()
          ctx.moveTo(p1.x + nx * desplazamiento, p1.y + ny * desplazamiento)
          ctx.lineTo(p2.x + nx * desplazamiento, p2.y + ny * desplazamiento)
          ctx.stroke()
        }
      } else if (familia === 'hueco') {
        // Solo el vano: dos jambas cortas y nada en medio.
        ctx.lineWidth = 2
        for (const p of [p1, p2]) {
          ctx.beginPath()
          ctx.moveTo(p.x - nx * 3, p.y - ny * 3)
          ctx.lineTo(p.x + nx * 3, p.y + ny * 3)
          ctx.stroke()
        }
      } else {
        ctx.lineWidth = 4
        ctx.beginPath()
        ctx.moveTo(p1.x, p1.y)
        ctx.lineTo(p2.x, p2.y)
        ctx.stroke()
      }
      ctx.restore()
    }

    // Cotas de cada tramo, en el punto medio.
    ctx.font = 'bold 11px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const tramos = cerrado ? puntos.length : puntos.length - 1
    for (let i = 0; i < tramos; i++) {
      // La cifra sale de las coordenadas ORIGINALES (medida real); la
      // posición del cartel, del tramo ya rectificado (donde se ve la línea).
      const a = puntos[i]
      const b = puntos[(i + 1) % puntos.length]
      const largo = Math.hypot(b.x - a.x, b.z - a.z)
      const sa = aPantalla(rectos[i])
      const sb = aPantalla(rectos[(i + 1) % rectos.length])
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
    rectos.forEach((p, i) => {
      const s = aPantalla(p)
      const ultimo = i === rectos.length - 1 && !cerrado
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
  }, [puntos, cerrado, posicionActual, elementos])

  return <canvas ref={lienzoRef} style={{ width: '100%', height: '100%', display: 'block' }} />
}
