import type { ReactNode } from 'react'
import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Icon } from './Icon'
import type { NombreIcono } from './Icon'
import { Tooltip, useEscapeCierra } from './ui'
import { useSidebarColapsada } from '../lib/sidebarColapsada'

export interface PestanaFicha {
  id: string
  etiqueta: string
  icono: NombreIcono
  contenido: ReactNode
}

/** Ficha genérica de un objeto complejo (presupuesto, certificación,
 *  factura, obra, tercero, banco de precios...) — Fase 27: cabecera con los
 *  datos principales y acciones, más pestañas para el resto.
 *
 *  Convención de pestañas (se va rellenando fase a fase, no todas existen
 *  todavía en cada ficha): la primera es siempre el contenido propio de la
 *  entidad; "Contactos" es la segunda cuando la entidad los tiene
 *  (Fase 27/28); "CRM" y "Documentos" van después cuando existan
 *  (Fase 29/30); "Historial" (Fase 38) es siempre la última — de ahí que
 *  este componente no las imponga, solo las ordene si la pantalla que lo usa
 *  las incluye en `pestanas`.
 *
 *  Reemplaza a `ModalPantalla` para estas pantallas (mismo look de modal a
 *  pantalla completa, misma tecla Escape para cerrar) — `ModalPantalla` sigue
 *  siendo la elección correcta para una ficha de una sola sección. */
export function FichaDetalle({
  titulo,
  subtitulo,
  acciones,
  pestanas,
  onClose,
}: {
  titulo: ReactNode
  subtitulo?: ReactNode
  acciones?: ReactNode
  pestanas: PestanaFicha[]
  onClose: () => void
}) {
  const [activaId, setActivaId] = useState(pestanas[0]?.id)
  const activa = pestanas.find((p) => p.id === activaId) ?? pestanas[0]
  const [colapsada, alternarColapsada] = useSidebarColapsada()

  // Por la pila de capas: si esta ficha tiene un modal abierto, el Escape es
  // suyo, no de la ficha (ver `useEscapeCierra`).
  useEscapeCierra(onClose)

  return (
    <div className="modal-pantalla-backdrop" onClick={onClose}>
      <div
        className="modal-pantalla"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-pantalla__head">
          <div className="modal-pantalla__head-izq">
            {/* La ficha tapa la topbar entera (con el botón de recoger la
                barra lateral) — mismo interruptor (`sidebarColapsada.ts`),
                repetido aquí para que siga habiendo forma de llegar a él. */}
            <Tooltip texto={colapsada ? 'Mostrar el menú' : 'Ocultar el menú'} posicion="abajo">
              <button
                className="modal-pantalla__colapsar"
                onClick={alternarColapsada}
                aria-label={colapsada ? 'Mostrar el menú' : 'Ocultar el menú'}
                aria-expanded={!colapsada}
              >
                {colapsada ? (
                  <ChevronRight size={16} aria-hidden="true" />
                ) : (
                  <ChevronLeft size={16} aria-hidden="true" />
                )}
              </button>
            </Tooltip>
            <span className="modal-pantalla__title">{titulo}</span>
          </div>
          <Tooltip texto="Cerrar" posicion="abajo">
            <button className="modal-pantalla__close" onClick={onClose} aria-label="Cerrar">
              <Icon name="cerrar" />
            </button>
          </Tooltip>
        </div>

        {(subtitulo || acciones) && (
          <div className="ficha-cabecera">
            {subtitulo && <div className="ficha-cabecera__info">{subtitulo}</div>}
            {acciones && <div className="ficha-cabecera__acciones">{acciones}</div>}
          </div>
        )}

        <div className="ficha-pestanas" role="tablist">
          {pestanas.map((p) => (
            <button
              key={p.id}
              type="button"
              role="tab"
              aria-selected={p.id === activa?.id}
              className={
                p.id === activa?.id ? 'ficha-pestana ficha-pestana--activa' : 'ficha-pestana'
              }
              onClick={() => setActivaId(p.id)}
            >
              <Icon name={p.icono} />
              {p.etiqueta}
            </button>
          ))}
        </div>

        <div className="modal-pantalla__body">{activa?.contenido}</div>
      </div>
    </div>
  )
}
