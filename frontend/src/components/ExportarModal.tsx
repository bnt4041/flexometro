import { useState } from 'react'
import { Download, X } from 'lucide-react'

import { ErrorNotice, Modal } from './ui'
import { api, descargar } from '../lib/api'

/** BC3/Excel con lo que se quiera llevar (Fase 39). En BC3 coste/venta son
 *  excluyentes —el formato solo admite un precio por línea—, así que se
 *  muestran como radio; en Excel van en columnas separadas, sin ese límite. */
export function ExportarModal({
  presupuestoId,
  codigo,
  formato,
  onClose,
}: {
  presupuestoId: string
  codigo: string
  formato: 'bc3' | 'excel'
  onClose: () => void
}) {
  const [precio, setPrecio] = useState<'coste' | 'venta'>('coste')
  const [coste, setCoste] = useState(true)
  const [venta, setVenta] = useState(false)
  const [descompuestos, setDescompuestos] = useState(formato === 'bc3')
  const [mediciones, setMediciones] = useState(formato === 'bc3')
  const [descripcion, setDescripcion] = useState(formato === 'bc3')
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  async function descargarAhora() {
    setOcupado(true)
    setError(null)
    try {
      if (formato === 'bc3') {
        await descargar(
          api.fiebdc.exportarUrl(presupuestoId, {
            venta: precio === 'venta',
            descompuestos,
            mediciones,
            descripcion,
          }),
          `${codigo}.bc3`,
        )
      } else {
        await descargar(
          api.presupuestos.excelUrl(presupuestoId, { coste, venta, descompuestos, mediciones, descripcion }),
          `${codigo}.xlsx`,
        )
      }
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  return (
    <Modal title={formato === 'bc3' ? 'Exportar a BC3' : 'Exportar a Excel'} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />

        {formato === 'bc3' ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
            <p className="form-section__note">
              Un BC3 solo admite un precio por línea: elige cuál llevar.
            </p>
            <label className="checkbox">
              <input
                type="radio"
                name="precio-bc3"
                checked={precio === 'coste'}
                onChange={() => setPrecio('coste')}
              />
              <span>Coste</span>
            </label>
            <label className="checkbox">
              <input
                type="radio"
                name="precio-bc3"
                checked={precio === 'venta'}
                onChange={() => {
                  setPrecio('venta')
                  setDescompuestos(false)
                }}
              />
              <span>Venta</span>
            </label>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
            <label className="checkbox">
              <input type="checkbox" checked={coste} onChange={(e) => setCoste(e.target.checked)} />
              <span>Coste</span>
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={venta} onChange={(e) => setVenta(e.target.checked)} />
              <span>Venta</span>
            </label>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={descompuestos}
              onChange={(e) => setDescompuestos(e.target.checked)}
              disabled={formato === 'bc3' && precio === 'venta'}
            />
            <span>Descompuestos</span>
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={mediciones} onChange={(e) => setMediciones(e.target.checked)} />
            <span>Mediciones</span>
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={descripcion} onChange={(e) => setDescripcion(e.target.checked)} />
            <span>Descripción</span>
          </label>
        </div>
        {formato === 'bc3' && precio === 'venta' && (
          <p className="form-section__note">
            Con venta no se exporta el cuadro de precios: el precio de cada partida ya no es un
            desglose, es un valor cerrado.
          </p>
        )}
      </div>

      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={ocupado || (formato === 'excel' && !coste && !venta)} onClick={() => void descargarAhora()}>
          <Download size={16} aria-hidden="true" />
          {ocupado ? 'Descargando…' : 'Descargar'}
        </button>
      </div>
    </Modal>
  )
}
