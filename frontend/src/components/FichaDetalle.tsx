import type { ReactNode } from 'react'
import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Icon } from './Icon'
import type { NombreIcono } from './Icon'
import { Tooltip } from './ui'
import { useSidebarColapsada } from '../lib/sidebarColapsada'

export interface PestanaFicha {
  id: string
  etiqueta: string
  icono: NombreIcono
  contenido: ReactNode
}

/** Ficha genérica de un objeto complejo (presupuesto, certificación,
 *  factura, obra, tercero, banco de precios...) — Fase 27: cabecera con los
 *  datos principales, más pestañas para el resto.
 *
 *  La cabecera NO lleva botones (Fase 43): cada ficha tenía la mitad de sus
 *  acciones aquí y la otra mitad en la barra del formulario, dos filas de
 *  botones para lo mismo. Ahora cada pestaña pone las suyas en una única
 *  barra al final de su contenido, que además es donde de verdad aplican
 *  (guardar afecta al formulario de esa pestaña, no a la ficha entera).
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
 *  pantalla completa) — `ModalPantalla` sigue siendo la elección correcta
 *  para una ficha de una sola sección.
 *
 *  Escape NO la cierra a propósito, igual que `Modal`: es fácil pulsarla sin
 *  querer al cancelar una edición de celda o cerrar un desplegable de dentro,
 *  y perder toda la ficha (y la posición en la que estabas) por eso es peor
 *  que tener que ir a la X a propósito. */
export function FichaDetalle({
  titulo,
  subtitulo,
  pestanas,
  onClose,
  pestanaActiva,
  onPestana,
}: {
  titulo: ReactNode
  subtitulo?: ReactNode
  pestanas: PestanaFicha[]
  onClose: () => void
  /** Para llevar a alguien a una pestaña desde dentro de otra (Mediciones
   *  manda al plano, por ejemplo). Sin esto la ficha se apaña sola, que es lo
   *  normal: solo se controla desde fuera cuando hace falta ese salto. */
  pestanaActiva?: string
  onPestana?: (id: string) => void
}) {
  const [activaInterna, setActivaInterna] = useState(pestanas[0]?.id)
  const activaId = pestanaActiva ?? activaInterna
  const setActivaId = (id: string) => {
    setActivaInterna(id)
    onPestana?.(id)
  }
  const activa = pestanas.find((p) => p.id === activaId) ?? pestanas[0]
  const [colapsada, alternarColapsada] = useSidebarColapsada()

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

        {subtitulo && (
          <div className="ficha-cabecera">
            <div className="ficha-cabecera__info">{subtitulo}</div>
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
