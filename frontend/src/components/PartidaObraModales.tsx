/** Dos ventanas auxiliares de la partida de obra, invocadas desde el botón
 *  derecho de `RejillaObra`:
 *
 *  - `DescompuestoObraModal`: el descompuesto que tenía la partida EN EL
 *    PRESUPUESTO de origen, de solo lectura. La obra no lleva descompuesto
 *    propio a propósito (el coste real sale de albaranes y partes de
 *    trabajo, no de un desglose teórico) — esto es solo para poder
 *    consultar con qué se calculó el precio contratado.
 *  - `DescripcionObraModal`: el mismo editor de texto enriquecido que usa
 *    presupuestos, aplicado al `texto` de la partida u obra de la OBRA. Es
 *    independiente del texto del presupuesto: se copia al vincular y desde
 *    ahí cada uno sigue el suyo, igual que el resto del árbol de obra.
 */

import { useEffect, useState } from 'react'
import { X } from 'lucide-react'

import { api } from '../lib/api'
import type { DescomposicionPartida } from '../lib/api'
import { ETIQUETA_NATURALEZA } from '../lib/api'
import { DescripcionEditor } from './DescripcionEditor'
import { EmptyState, ErrorNotice, Modal, formatoImporte } from './ui'

export function DescompuestoObraModal({
  origenPartidaId,
  origenCodigo,
  titulo,
  onClose,
}: {
  origenPartidaId: string
  origenCodigo: string | null
  titulo: string
  onClose: () => void
}) {
  const [datos, setDatos] = useState<DescomposicionPartida | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let vigente = true
    api.partidas
      .descomposicion(origenPartidaId)
      .then((d) => vigente && setDatos(d))
      .catch((err: unknown) => {
        if (vigente) setError(err instanceof Error ? err.message : 'Error desconocido')
      })
    return () => {
      vigente = false
    }
  }, [origenPartidaId])

  return (
    <Modal title={`Descompuesto contratado — ${titulo}`} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="aceptar__intro">
          Con lo que se calculó el precio en {origenCodigo ?? 'el presupuesto de origen'}. Solo
          lectura: en obra no se edita aquí — el coste real de esta partida sale de sus albaranes y
          partes de trabajo.
        </p>

        {datos === null && !error ? (
          <p className="muted">Cargando…</p>
        ) : datos && datos.lineas.length === 0 ? (
          <EmptyState title="Sin descompuesto">
            Esta partida no tenía descompuesto en el presupuesto de origen: su precio se tecleó
            directamente.
          </EmptyState>
        ) : datos ? (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Descripción</th>
                  <th>Naturaleza</th>
                  <th className="table__num">Rendimiento</th>
                  <th className="table__num">Precio</th>
                  <th className="table__num">Importe</th>
                </tr>
              </thead>
              <tbody>
                {datos.lineas.map((l) => (
                  <tr key={l.id}>
                    <td className="table__code">{l.codigo || '—'}</td>
                    <td>{l.resumen}</td>
                    <td>{l.naturaleza ? ETIQUETA_NATURALEZA[l.naturaleza] : <span className="muted">—</span>}</td>
                    <td className="table__num">
                      {formatoImporte(l.rendimiento, 3)} {l.unidad}
                    </td>
                    <td className="table__num">{formatoImporte(l.precio)}</td>
                    <td className="table__num">
                      <strong>{formatoImporte(l.importe)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cerrar
        </button>
      </div>
    </Modal>
  )
}

export function DescripcionObraModal({
  id,
  obraId,
  titulo,
  html,
  onGuardar,
  onClose,
}: {
  /** El id de la fila (capítulo o partida): fuerza al editor a partir de cero
   *  si se abriera para otra distinta sin desmontarse por medio. */
  id: string
  obraId: string
  titulo: string
  html: string | null
  onGuardar: (html: string) => Promise<void>
  onClose: () => void
}) {
  return (
    <Modal title={`Descripción ampliada — ${titulo}`} onClose={onClose}>
      <DescripcionEditor
        key={id}
        id={id}
        html={html}
        entidad="obra"
        entidadId={obraId}
        onGuardar={onGuardar}
      />
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cerrar
        </button>
      </div>
    </Modal>
  )
}
