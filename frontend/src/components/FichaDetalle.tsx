import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'

import { Icon } from './Icon'
import type { NombreIcono } from './Icon'
import { Tooltip } from './ui'

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
 *  (Fase 27/28); "CRM" y "Documentos" son las últimas dos cuando existan
 *  (Fase 29/30) — de ahí que este componente no las imponga, solo las ordene
 *  si la pantalla que lo usa las incluye en `pestanas`.
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

  useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', alPulsar)
    return () => window.removeEventListener('keydown', alPulsar)
  }, [onClose])

  return (
    <div className="modal-pantalla-backdrop" onClick={onClose}>
      <div
        className="modal-pantalla"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-pantalla__head">
          <span className="modal-pantalla__title">{titulo}</span>
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

        <div className="modal-pantalla__body">
          <div className="content__inner">{activa?.contenido}</div>
        </div>
      </div>
    </div>
  )
}
