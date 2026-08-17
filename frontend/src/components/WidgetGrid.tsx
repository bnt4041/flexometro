import type { ReactNode } from 'react'
import { useState } from 'react'
import { GridLayout, useContainerWidth } from 'react-grid-layout'
import type { Layout, LayoutItem } from 'react-grid-layout'
import { GripVertical, Plus, X, ZoomIn, ZoomOut } from 'lucide-react'

import { Tooltip } from './ui'

import 'react-grid-layout/css/styles.css'

export interface Widget {
  id: string
  titulo: string
  contenido: ReactNode
  /** Posición y tamaño por defecto, en unidades de rejilla (12 columnas). */
  x: number
  y: number
  w: number
  h: number
  minW?: number
  minH?: number
}

const ZOOM_MIN = 0.6
const ZOOM_MAX = 1.6
const ZOOM_PASO = 0.1

interface EstadoGuardado {
  layout: LayoutItem[]
  ocultos: string[]
  zoom: Record<string, number>
}

function cargarEstado(id: string, defecto: Layout): EstadoGuardado {
  try {
    const crudo = localStorage.getItem(`grid:${id}`)
    if (!crudo) return { layout: [...defecto], ocultos: [], zoom: {} }
    const parsed = JSON.parse(crudo) as LayoutItem[] | Partial<EstadoGuardado>
    // Formato viejo (Fase 31 inicial): un array de posiciones, sin ocultos ni zoom.
    const guardado = Array.isArray(parsed) ? parsed : (parsed.layout ?? [])
    const ocultos = Array.isArray(parsed) ? [] : (parsed.ocultos ?? [])
    const zoom = Array.isArray(parsed) ? {} : (parsed.zoom ?? {})
    const porId = new Map(guardado.map((item) => [item.i, item]))
    // Se parte siempre de los widgets que existen HOY: si una fase futura
    // añade o quita un widget, no se hereda una posición fantasma ni se
    // pierde uno nuevo por culpa de un layout guardado de una versión vieja.
    const layout = defecto.map((d) => porId.get(d.i) ?? d)
    const idsHoy = new Set(defecto.map((d) => d.i))
    return {
      layout,
      ocultos: ocultos.filter((o) => idsHoy.has(o)),
      zoom: Object.fromEntries(Object.entries(zoom).filter(([i]) => idsHoy.has(i))),
    }
  } catch {
    return { layout: [...defecto], ocultos: [], zoom: {} }
  }
}

function guardarEstado(id: string, estado: EstadoGuardado) {
  try {
    localStorage.setItem(`grid:${id}`, JSON.stringify(estado))
  } catch {
    /* localStorage lleno o bloqueado: el grid sigue funcionando, solo no recuerda la disposición */
  }
}

/** Grid de widgets arrastrables y redimensionables (Fase 31) — el usuario
 *  reordena y ajusta el tamaño de cada sección a su gusto, puede quitar un
 *  widget del lienzo (y volver a traerlo) y hacer zoom sobre su contenido
 *  por separado del tamaño de la casilla; esa disposición se recuerda en
 *  `localStorage` de su navegador (por `id`, no por cuenta: cada persona ve
 *  su propia disposición en su propio equipo). Se arrastra solo por la
 *  cabecera de cada widget (el icono ⠿), para no competir con el scroll o
 *  la selección de texto dentro del contenido. */
export function WidgetGrid({ id, widgets }: { id: string; widgets: Widget[] }) {
  const defecto: Layout = widgets.map((w) => ({
    i: w.id,
    x: w.x,
    y: w.y,
    w: w.w,
    h: w.h,
    minW: w.minW,
    minH: w.minH,
  }))
  const [estado, setEstado] = useState<EstadoGuardado>(() => cargarEstado(id, defecto))
  const { width, containerRef, mounted } = useContainerWidth()

  const visibles = widgets.filter((w) => !estado.ocultos.includes(w.id))
  const ocultos = widgets.filter((w) => estado.ocultos.includes(w.id))
  const layoutVisible = estado.layout.filter((item) => !estado.ocultos.includes(item.i))

  function actualizar(cambios: Partial<EstadoGuardado>) {
    setEstado((previo) => {
      const nuevo = { ...previo, ...cambios }
      guardarEstado(id, nuevo)
      return nuevo
    })
  }

  function cambiarLayout(nuevoLayoutVisible: Layout) {
    const porId = new Map(nuevoLayoutVisible.map((item) => [item.i, item]))
    actualizar({ layout: estado.layout.map((item) => porId.get(item.i) ?? item) })
  }

  function ocultar(widgetId: string) {
    actualizar({ ocultos: [...estado.ocultos, widgetId] })
  }

  function mostrar(widgetId: string) {
    actualizar({ ocultos: estado.ocultos.filter((o) => o !== widgetId) })
  }

  function zoomDe(widgetId: string): number {
    return estado.zoom[widgetId] ?? 1
  }

  function cambiarZoom(widgetId: string, delta: number) {
    const nuevo = Math.min(
      ZOOM_MAX,
      Math.max(ZOOM_MIN, Math.round((zoomDe(widgetId) + delta) * 10) / 10),
    )
    actualizar({ zoom: { ...estado.zoom, [widgetId]: nuevo } })
  }

  function restablecerZoom(widgetId: string) {
    actualizar({ zoom: { ...estado.zoom, [widgetId]: 1 } })
  }

  return (
    <div className="widget-grid-wrap">
      {ocultos.length > 0 && (
        <div className="widget-grid__ocultos">
          <span className="muted">Ocultos:</span>
          {ocultos.map((w) => (
            <button key={w.id} className="btn btn--sm" onClick={() => mostrar(w.id)}>
              <Plus size={14} aria-hidden="true" />
              {w.titulo}
            </button>
          ))}
        </div>
      )}

      <div ref={containerRef} className="widget-grid">
        {mounted && (
          <GridLayout
            width={width}
            layout={layoutVisible}
            gridConfig={{ cols: 12, rowHeight: 30, margin: [16, 16] }}
            dragConfig={{ handle: '.widget__asa' }}
            onLayoutChange={cambiarLayout}
          >
            {visibles.map((w) => {
              const zoom = zoomDe(w.id)
              return (
                <div key={w.id} className="widget">
                  <div className="widget__cabecera">
                    <span className="widget__asa" title="Arrastrar para mover">
                      <GripVertical size={14} aria-hidden="true" />
                    </span>
                    <span className="widget__titulo">{w.titulo}</span>
                    <div className="widget__zoom">
                      <Tooltip texto="Reducir">
                        <button
                          className="widget__zoom-btn"
                          disabled={zoom <= ZOOM_MIN}
                          onClick={() => cambiarZoom(w.id, -ZOOM_PASO)}
                        >
                          <ZoomOut size={14} aria-hidden="true" />
                        </button>
                      </Tooltip>
                      <Tooltip texto="Restablecer zoom">
                        <button className="widget__zoom-valor" onClick={() => restablecerZoom(w.id)}>
                          {Math.round(zoom * 100)}%
                        </button>
                      </Tooltip>
                      <Tooltip texto="Ampliar">
                        <button
                          className="widget__zoom-btn"
                          disabled={zoom >= ZOOM_MAX}
                          onClick={() => cambiarZoom(w.id, ZOOM_PASO)}
                        >
                          <ZoomIn size={14} aria-hidden="true" />
                        </button>
                      </Tooltip>
                    </div>
                    <Tooltip texto="Quitar del lienzo">
                      <button className="widget__cerrar" onClick={() => ocultar(w.id)}>
                        <X size={14} aria-hidden="true" />
                      </button>
                    </Tooltip>
                  </div>
                  <div className="widget__cuerpo">
                    <div
                      className="widget__zoom-lienzo"
                      style={{ transform: `scale(${zoom})`, width: `${100 / zoom}%` }}
                    >
                      {w.contenido}
                    </div>
                  </div>
                </div>
              )
            })}
          </GridLayout>
        )}
      </div>
    </div>
  )
}
