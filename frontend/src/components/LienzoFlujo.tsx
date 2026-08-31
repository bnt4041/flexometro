import { useCallback, useRef, useState } from 'react'
import { Trash2, X } from 'lucide-react'

import { Icon } from './Icon'
import type { NombreIcono } from './Icon'
import type { DefinicionFlujo, NodoFlujo, TipoNodo } from '../lib/api'

const ANCHO_NODO = 210
const ALTO_NODO = 68

/** El lienzo donde se monta el flujo.
 *
 *  Conectar es «pulsar la salida, pulsar el destino» y no arrastrar de un
 *  punto a otro. Arrastrar queda más vistoso, pero falla justo donde peor
 *  sienta: con el dedo, con el lienzo desplazado o cuando el destino está
 *  fuera de pantalla. En dos toques siempre funciona.
 *
 *  Los nodos SÍ se arrastran, porque ahí la posición es lo que se manipula y
 *  no hay ambigüedad posible. */
export function LienzoFlujo({
  definicion,
  tipos,
  seleccionado,
  onSeleccionar,
  onCambio,
  pasosPorNodo,
}: {
  definicion: DefinicionFlujo
  tipos: TipoNodo[]
  seleccionado: string | null
  onSeleccionar: (id: string | null) => void
  onCambio: (definicion: DefinicionFlujo) => void
  /** Resultado de la última prueba, para pintar por dónde fue. */
  pasosPorNodo?: Record<string, { estado: string; ruta: string | null }>
}) {
  const lienzoRef = useRef<HTMLDivElement>(null)
  const arrastreRef = useRef<{ id: string; dx: number; dy: number } | null>(null)
  const [conectandoDe, setConectandoDe] = useState<{ nodo: string; salida: string } | null>(null)

  const tipoDe = useCallback(
    (nodo: NodoFlujo) => tipos.find((t) => t.tipo === nodo.tipo),
    [tipos],
  )

  const posicion = (nodo: NodoFlujo) => ({ x: nodo.x ?? 40, y: nodo.y ?? 40 })

  function empezarArrastre(e: React.PointerEvent, nodo: NodoFlujo) {
    // Los botones de dentro (los puntos de salida y el de borrar) no
    // arrastran. Y es más que cosmético: `setPointerCapture` desvía TODOS
    // los eventos siguientes a este div, así que el botón nunca llegaría a
    // recibir su clic y no habría forma de conectar nada.
    if ((e.target as HTMLElement).closest('button')) return
    e.currentTarget.setPointerCapture(e.pointerId)
    const caja = lienzoRef.current!.getBoundingClientRect()
    const { x, y } = posicion(nodo)
    arrastreRef.current = {
      id: nodo.id,
      dx: e.clientX - caja.left - x,
      dy: e.clientY - caja.top - y,
    }
  }

  function mover(e: React.PointerEvent) {
    const arrastre = arrastreRef.current
    if (!arrastre) return
    const caja = lienzoRef.current!.getBoundingClientRect()
    onCambio({
      ...definicion,
      nodos: definicion.nodos.map((n) =>
        n.id === arrastre.id
          ? {
              ...n,
              // Sin negativos: un nodo arrastrado fuera por la izquierda se
              // quedaría inalcanzable, porque el lienzo no se desplaza.
              x: Math.max(0, e.clientX - caja.left - arrastre.dx),
              y: Math.max(0, e.clientY - caja.top - arrastre.dy),
            }
          : n,
      ),
    })
  }

  function conectar(hasta: string) {
    if (!conectandoDe) return
    if (conectandoDe.nodo === hasta) {
      // Un nodo consigo mismo es un ciclo garantizado. El motor lo corta,
      // pero dejarlo dibujar es invitar a un flujo que no hace nada.
      setConectandoDe(null)
      return
    }
    const sinLaVieja = definicion.conexiones.filter(
      (c) => !(c.desde === conectandoDe.nodo && c.salida === conectandoDe.salida),
    )
    onCambio({
      ...definicion,
      // Una salida va a UN sitio: si fuera a varios, habría que decidir el
      // orden y qué pasa si uno falla. Eso es otra conversación.
      conexiones: [...sinLaVieja, { desde: conectandoDe.nodo, salida: conectandoDe.salida, hasta }],
    })
    setConectandoDe(null)
  }

  function quitarNodo(id: string) {
    onCambio({
      nodos: definicion.nodos.filter((n) => n.id !== id),
      conexiones: definicion.conexiones.filter((c) => c.desde !== id && c.hasta !== id),
    })
    if (seleccionado === id) onSeleccionar(null)
  }

  /** Curva de la salida de un nodo a la entrada de otro. */
  function curva(desde: NodoFlujo, hasta: NodoFlujo, indiceSalida: number, total: number) {
    const a = posicion(desde)
    const b = posicion(hasta)
    const x1 = a.x + ANCHO_NODO
    const y1 = a.y + (ALTO_NODO * (indiceSalida + 1)) / (total + 1)
    const x2 = b.x
    const y2 = b.y + ALTO_NODO / 2
    const tension = Math.max(40, Math.abs(x2 - x1) / 2)
    return `M ${x1} ${y1} C ${x1 + tension} ${y1}, ${x2 - tension} ${y2}, ${x2} ${y2}`
  }

  const alto = Math.max(
    420,
    ...definicion.nodos.map((n) => posicion(n).y + ALTO_NODO + 60),
  )

  return (
    <div
      ref={lienzoRef}
      onPointerMove={mover}
      onPointerUp={() => (arrastreRef.current = null)}
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onSeleccionar(null)
          setConectandoDe(null)
        }
      }}
      style={{
        position: 'relative',
        height: alto,
        overflow: 'auto',
        border: '1px solid var(--c-border)',
        borderRadius: 8,
        background:
          'var(--c-surface-2) radial-gradient(var(--c-border) 1px, transparent 1px) 0 0 / 18px 18px',
      }}
    >
      <svg
        style={{ position: 'absolute', inset: 0, width: '100%', height: alto, pointerEvents: 'none' }}
      >
        {definicion.conexiones.map((conexion, i) => {
          const desde = definicion.nodos.find((n) => n.id === conexion.desde)
          const hasta = definicion.nodos.find((n) => n.id === conexion.hasta)
          if (!desde || !hasta) return null
          const salidas = tipoDe(desde)?.salidas ?? [['principal', 'Salida']]
          const indice = Math.max(0, salidas.findIndex(([s]) => s === conexion.salida))
          return (
            <path
              key={i}
              d={curva(desde, hasta, indice, salidas.length)}
              fill="none"
              stroke="var(--c-accent-strong, #f59e0b)"
              strokeWidth={2}
            />
          )
        })}
      </svg>

      {definicion.nodos.map((nodo) => {
        const tipo = tipoDe(nodo)
        const { x, y } = posicion(nodo)
        const salidas = tipo?.salidas ?? [['principal', 'Salida']]
        const paso = pasosPorNodo?.[nodo.id]
        return (
          <div
            key={nodo.id}
            onPointerDown={(e) => empezarArrastre(e, nodo)}
            onClick={(e) => {
              e.stopPropagation()
              if (conectandoDe) conectar(nodo.id)
              else onSeleccionar(nodo.id)
            }}
            style={{
              position: 'absolute',
              left: x,
              top: y,
              width: ANCHO_NODO,
              minHeight: ALTO_NODO,
              padding: '8px 10px',
              borderRadius: 8,
              cursor: conectandoDe ? 'crosshair' : 'grab',
              background: 'var(--c-surface)',
              border: `2px solid ${
                seleccionado === nodo.id
                  ? 'var(--c-accent-strong, #f59e0b)'
                  : paso?.estado === 'error'
                    ? 'var(--c-danger, #dc2626)'
                    : paso?.estado === 'ok'
                      ? 'var(--c-ok, #16a34a)'
                      : 'var(--c-border)'
              }`,
              boxShadow: '0 1px 3px rgba(0,0,0,.12)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600 }}>
              <Icon name={(tipo?.icono ?? 'square') as NombreIcono} size={14} />
              <span style={{ flex: 1, fontSize: '0.9em' }}>
                {nodo.nombre || tipo?.etiqueta || nodo.tipo}
              </span>
              <button
                className="btn btn--sm"
                aria-label="Quitar nodo"
                onClick={(e) => {
                  e.stopPropagation()
                  quitarNodo(nodo.id)
                }}
                style={{ padding: 2 }}
              >
                <Trash2 size={11} aria-hidden="true" />
              </button>
            </div>
            {tipo?.categoria === 'disparador' && (
              <div className="muted" style={{ fontSize: '0.75em' }}>
                arranque
              </div>
            )}

            {/* Los puntos de salida, uno por rama. */}
            {salidas.map(([clave, etiqueta], i) => (
              <button
                key={clave}
                title={`Conectar desde «${etiqueta}»`}
                onClick={(e) => {
                  e.stopPropagation()
                  setConectandoDe({ nodo: nodo.id, salida: clave })
                }}
                style={{
                  position: 'absolute',
                  right: -9,
                  top: (ALTO_NODO * (i + 1)) / (salidas.length + 1) - 8,
                  width: 16,
                  height: 16,
                  borderRadius: '50%',
                  border: '2px solid var(--c-surface)',
                  background:
                    conectandoDe?.nodo === nodo.id && conectandoDe.salida === clave
                      ? 'var(--c-accent-strong, #f59e0b)'
                      : 'var(--c-text-muted, #6b7280)',
                  cursor: 'pointer',
                  padding: 0,
                }}
              />
            ))}
            {salidas.length > 1 && (
              <div
                className="muted"
                style={{ position: 'absolute', right: -46, top: 4, fontSize: '0.65em' }}
              >
                {salidas.map(([, etiqueta]) => (
                  <div key={etiqueta} style={{ height: 24 }}>
                    {etiqueta}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}

      {conectandoDe && (
        <div
          className="notice"
          // Abajo y no arriba: arriba es justo donde caen los primeros
          // nodos, y el aviso tapaba el que estabas conectando.
          style={{ position: 'absolute', left: 12, bottom: 12, margin: 0, fontSize: '0.85em' }}
        >
          Pulsa el nodo al que quieres llegar.
          <button
            className="btn btn--sm"
            onClick={(e) => {
              e.stopPropagation()
              setConectandoDe(null)
            }}
            style={{ marginLeft: 8 }}
          >
            <X size={12} aria-hidden="true" /> Cancelar
          </button>
        </div>
      )}

      {definicion.nodos.length === 0 && (
        <p
          className="muted"
          style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}
        >
          Añade el nodo que arranca el flujo para empezar.
        </p>
      )}
    </div>
  )
}
