import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Ban, FileDown, Plus, RefreshCw, Send, Trash2, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { ETIQUETA_ESTADO_FACTURA, ETIQUETA_SITUACION_COBRO, api, descargar } from '../lib/api'
import type { FacturaDetalle as Detalle } from '../lib/api'
import { useContextoFacturas } from './Facturas'

export function FacturaDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoFacturas()
  const [factura, setFactura] = useState<Detalle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [anulando, setAnulando] = useState(false)
  const [cobrando, setCobrando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setFactura(await api.facturas.get(id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/facturas')
  }

  if (error && !factura) {
    return (
      <ModalPantalla title="Factura" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!factura) return null

  async function emitir() {
    try {
      await api.facturas.emitir(id)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function reintentarNotificacion() {
    try {
      const actualizada = await api.facturas.notificar(id)
      await cargar()
      setAviso(
        actualizada.notificado_n8n_en
          ? 'Notificada a n8n correctamente.'
          : 'n8n no ha respondido; sigue pendiente de enviar.',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminarCobro(cobroId: string) {
    await api.cobros.remove(cobroId)
    await cargar()
  }

  const numeroFiscal = factura.numero
    ? `${factura.serie}/${String(factura.numero).padStart(5, '0')}`
    : `${factura.serie} · borrador`

  return (
    <ModalPantalla
      title={
        <>
          {factura.cliente_razon_social} <span className="table__code">{numeroFiscal}</span>
        </>
      }
      onClose={cerrar}
    >
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          {factura.concepto}
          {factura.fecha_emision && <> · emitida {factura.fecha_emision}</>}
        </p>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <Tooltip texto="Descargar el PDF de esta factura">
            <button
              className="btn"
              onClick={() =>
                void descargar(api.facturas.pdfUrl(id), `${numeroFiscal.replace('/', '-')}.pdf`, {
                  abrir: true,
                }).catch((err) => setError(err instanceof Error ? err.message : String(err)))
              }
            >
              <FileDown size={16} aria-hidden="true" />
              PDF
            </button>
          </Tooltip>
          {factura.estado === 'borrador' && (
            <Tooltip texto="Emitir: asigna número fiscal definitivo">
              <button className="btn btn--primary" onClick={() => void emitir()}>
                <Send size={16} aria-hidden="true" />
                Emitir
              </button>
            </Tooltip>
          )}
          {factura.estado === 'emitida' && (
            <Tooltip texto="Anular esta factura (conserva su número)">
              <button className="btn btn--danger" onClick={() => setAnulando(true)}>
                <Ban size={16} aria-hidden="true" />
                Anular
              </button>
            </Tooltip>
          )}
        </div>
      </div>

      <ErrorNotice error={error} />
      {aviso && <div className="notice notice--ok">{aviso}</div>}

      <div className="page-head" style={{ marginBottom: 'var(--sp-2)' }}>
        <span className={`chip chip--estado-${factura.estado}`}>
          {ETIQUETA_ESTADO_FACTURA[factura.estado]}
        </span>
        {factura.estado === 'emitida' && (
          <span className={`chip chip--cobro-${factura.situacion_cobro}`}>
            {ETIQUETA_SITUACION_COBRO[factura.situacion_cobro]}
            {factura.vencida && ' · vencida'}
          </span>
        )}
      </div>

      {factura.estado === 'anulada' && factura.motivo_anulacion && (
        <div className="notice notice--error">Anulada: {factura.motivo_anulacion}</div>
      )}

      {factura.estado === 'emitida' && !factura.notificado_n8n_en && (
        <div className="notice notice--aviso">
          Todavía no se ha notificado a n8n para el circuito Veri*Factu/Facturae.{' '}
          <button className="btn btn--sm" onClick={() => void reintentarNotificacion()}>
            <RefreshCw size={14} aria-hidden="true" />
            Reintentar envío
          </button>
        </div>
      )}

      <div className="card resumen-totales">
        <div className="resumen-totales__fila">
          <span>Base imponible</span>
          <span className="resumen-totales__valor">{formatoImporte(factura.base_imponible)} €</span>
        </div>
        <div className="resumen-totales__fila is-suave">
          <span>{factura.inversion_sujeto_pasivo ? 'IVA — inversión del sujeto pasivo' : 'IVA'}</span>
          <span className="resumen-totales__valor">{formatoImporte(factura.cuota_iva)} €</span>
        </div>
        <div className="resumen-totales__fila is-total">
          <span>Total</span>
          <span className="resumen-totales__valor">{formatoImporte(factura.total)} €</span>
        </div>
      </div>

      {factura.estado === 'emitida' && (
        <>
          <div className="page-head" style={{ marginTop: 'var(--sp-6)' }}>
            <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Cobros</h2>
            {factura.situacion_cobro !== 'cobrada' && (
              <Tooltip texto="Registrar un cobro para esta factura">
                <button className="btn" onClick={() => setCobrando(true)}>
                  <Plus size={16} aria-hidden="true" />
                  Registrar cobro
                </button>
              </Tooltip>
            )}
          </div>

          <div className="table-wrap">
            {factura.cobros.length === 0 ? (
              <EmptyState title="Sin cobros registrados" />
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Forma de pago</th>
                    <th className="table__num">Importe</th>
                    <th className="table__actions" />
                  </tr>
                </thead>
                <tbody>
                  {factura.cobros.map((c) => (
                    <tr key={c.id}>
                      <td>{c.fecha}</td>
                      <td>{c.forma_pago ?? <span className="muted">—</span>}</td>
                      <td className="table__num">{formatoImporte(c.importe)}</td>
                      <td className="table__actions">
                        <Tooltip texto="Eliminar este cobro">
                          <button
                            className="btn btn--sm btn--danger btn--solo-icono"
                            onClick={() => void eliminarCobro(c.id)}
                          >
                            <Trash2 size={14} aria-hidden="true" />
                          </button>
                        </Tooltip>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="fila-total">
                    <td colSpan={2} className="table__num total-label">
                      Pendiente
                    </td>
                    <td className="table__num">
                      <strong>{formatoImporte(factura.pendiente)}</strong>
                    </td>
                    <td />
                  </tr>
                </tfoot>
              </table>
            )}
          </div>
        </>
      )}

      {anulando && (
        <AnularModal
          onClose={() => setAnulando(false)}
          onAnulada={() => {
            setAnulando(false)
            void cargar()
            onCambio()
          }}
          facturaId={id}
        />
      )}

      {cobrando && (
        <CobroModal
          facturaId={id}
          onClose={() => setCobrando(false)}
          onRegistrado={() => {
            setCobrando(false)
            void cargar()
            onCambio()
          }}
        />
      )}
    </ModalPantalla>
  )
}

function AnularModal({
  facturaId,
  onClose,
  onAnulada,
}: {
  facturaId: string
  onClose: () => void
  onAnulada: () => void
}) {
  const [motivo, setMotivo] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function confirmar() {
    setError(null)
    try {
      await api.facturas.anular(facturaId, motivo)
      onAnulada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Anular factura" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          La factura conserva su número: una factura emitida no se borra nunca, para no dejar
          huecos en la serie.
        </p>
        <Field label="Motivo de la anulación">
          <textarea
            className="input"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            autoFocus
          />
        </Field>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--danger"
          disabled={motivo.trim() === ''}
          onClick={() => void confirmar()}
        >
          <Ban size={16} aria-hidden="true" />
          Anular
        </button>
      </div>
    </Modal>
  )
}

function CobroModal({
  facturaId,
  onClose,
  onRegistrado,
}: {
  facturaId: string
  onClose: () => void
  onRegistrado: () => void
}) {
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [importe, setImporte] = useState('')
  const [formaPago, setFormaPago] = useState('transferencia')
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    setError(null)
    try {
      await api.facturas.addCobro(facturaId, { fecha, importe, forma_pago: formaPago })
      onRegistrado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Registrar cobro" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field label="Fecha">
            <input
              className="input"
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </Field>
          <Field label="Importe">
            <input
              className="input"
              type="number"
              step="0.01"
              value={importe}
              onChange={(e) => setImporte(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Forma de pago">
            <select className="select" value={formaPago} onChange={(e) => setFormaPago(e.target.value)}>
              <option value="transferencia">Transferencia</option>
              <option value="domiciliado">Domiciliado</option>
              <option value="pagare">Pagaré</option>
              <option value="confirming">Confirming</option>
              <option value="efectivo">Efectivo</option>
              <option value="tarjeta">Tarjeta</option>
            </select>
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={importe === ''} onClick={() => void guardar()}>
          <Plus size={16} aria-hidden="true" />
          Registrar
        </button>
      </div>
    </Modal>
  )
}
