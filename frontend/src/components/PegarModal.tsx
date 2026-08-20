import { Copy, Move, X } from 'lucide-react'

import { Modal } from './ui'
import type { AlcancePegado } from '../lib/api'

/** "¿Mover o copiar?" al pegar (Ctrl+V) o soltar un arrastre — Fase 1b/1d.
 *  El mismo diálogo para las tres rejillas (partidas, descompuesto,
 *  mediciones): lo único que cambia es de dónde viene y a dónde va. */
export function PegarModal({
  cantidad,
  origenEtiqueta,
  onElegir,
  onClose,
}: {
  cantidad: number
  origenEtiqueta: string
  onElegir: (alcance: AlcancePegado) => void
  onClose: () => void
}) {
  const texto = cantidad === 1 ? '1 elemento' : `${cantidad} elementos`

  return (
    <Modal title="¿Mover o copiar?" onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          Vas a pegar {texto} de «{origenEtiqueta}» aquí.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
          <button className="btn" onClick={() => onElegir('mover')}>
            <Move size={16} aria-hidden="true" />
            Mover aquí
          </button>
          <button className="btn btn--primary" onClick={() => onElegir('copiar')}>
            <Copy size={16} aria-hidden="true" />
            Copiar aquí
          </button>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
      </div>
    </Modal>
  )
}
