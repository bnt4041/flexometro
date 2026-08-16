import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ErrorNotice, Field, Modal, ModalPantalla, formatoImporte } from '../components/ui'
import { ETIQUETA_ESTADO_CERTIFICACION, api, descargar } from '../lib/api'
import type { CertificacionDetalle as Detalle, Obra } from '../lib/api'
import { useContextoCertificaciones } from './Certificaciones'

export function CertificacionDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoCertificaciones()
  const [certificacion, setCertificacion] = useState<Detalle | null>(null)
  const [obra, setObra] = useState<Obra | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [generando, setGenerando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const detalle = await api.certificaciones.get(id)
      setCertificacion(detalle)
      setObra(await api.obras.get(detalle.obra_id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/certificaciones')
  }

  if (error && !certificacion) {
    return (
      <ModalPantalla title="Certificación" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!certificacion) return null

  async function emitir() {
    try {
      await api.certificaciones.emitir(id)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar la certificación ${certificacion!.codigo}?`)) return
    try {
      await api.certificaciones.remove(id)
      onCambio()
      navigate(`/obras/${certificacion!.obra_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const esBorrador = certificacion.estado === 'borrador'

  return (
    <ModalPantalla
      title={
        <>
          Certificación nº {certificacion.numero}{' '}
          <span className="table__code">{certificacion.codigo}</span>
        </>
      }
      onClose={cerrar}
    >
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          {obra && <>Obra <Link to={`/obras/${obra.id}`}>{obra.codigo}</Link> · </>}
          {certificacion.fecha}{' '}
          <span className={`chip chip--estado-cert-${certificacion.estado}`}>
            {ETIQUETA_ESTADO_CERTIFICACION[certificacion.estado]}
          </span>
          {certificacion.facturada && <span className="badge"> facturada</span>}
        </p>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <button
            className="btn"
            onClick={() =>
              void descargar(
                api.certificaciones.pdfUrl(id),
                `${certificacion.codigo}.pdf`,
                { abrir: true },
              ).catch((err) => setError(err instanceof Error ? err.message : String(err)))
            }
          >
            PDF
          </button>
          {esBorrador ? (
            <>
              <button className="btn btn--danger" onClick={() => void eliminar()}>
                Eliminar
              </button>
              <button className="btn btn--primary" onClick={() => void emitir()}>
                Emitir
              </button>
            </>
          ) : (
            !certificacion.facturada && (
              <button className="btn btn--primary" onClick={() => setGenerando(true)}>
                Generar factura
              </button>
            )
          )}
        </div>
      </div>

      <ErrorNotice error={error} />

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Código</th>
              <th>Descripción</th>
              <th className="table__num">Anterior</th>
              <th className="table__num">Actual</th>
              <th className="table__num">Periodo</th>
              <th className="table__num">Precio</th>
              <th className="table__num">Importe</th>
            </tr>
          </thead>
          <tbody>
            {certificacion.lineas.map((l) => (
              <tr key={l.id}>
                <td className="table__code">{l.codigo}</td>
                <td>
                  {l.resumen} <span className="muted">({l.unidad})</span>
                </td>
                <td className="table__num muted">{formatoImporte(l.medicion_anterior, 3)}</td>
                <td className="table__num">{formatoImporte(l.medicion_actual, 3)}</td>
                <td className="table__num">{formatoImporte(l.medicion_periodo, 3)}</td>
                <td className="table__num">{formatoImporte(l.precio)}</td>
                <td className="table__num">
                  <strong>{formatoImporte(l.importe_periodo)}</strong>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card resumen-totales">
        <div className="resumen-totales__fila">
          <span>Importe ejecutado en este periodo</span>
          <span className="resumen-totales__valor">
            {formatoImporte(certificacion.importe_ejecutado)} €
          </span>
        </div>
        {Number(certificacion.retencion_garantia_pct) > 0 && (
          <div className="resumen-totales__fila is-suave">
            <span>Retención de garantía ({formatoImporte(certificacion.retencion_garantia_pct)} %)</span>
            <span className="resumen-totales__valor">
              -{formatoImporte(certificacion.importe_retenido)} €
            </span>
          </div>
        )}
        <div className="resumen-totales__fila is-total">
          <span>Líquido a certificar</span>
          <span className="resumen-totales__valor">
            {formatoImporte(certificacion.importe_liquido)} €
          </span>
        </div>
      </div>

      {generando && (
        <GenerarFacturaModal
          certificacionId={id}
          onClose={() => setGenerando(false)}
          onGenerada={(facturaId) => {
            onCambio()
            navigate(`/facturas/${facturaId}`)
          }}
        />
      )}
    </ModalPantalla>
  )
}

function GenerarFacturaModal({
  certificacionId,
  onClose,
  onGenerada,
}: {
  certificacionId: string
  onClose: () => void
  onGenerada: (facturaId: string) => void
}) {
  const [serie, setSerie] = useState(String(new Date().getFullYear()))
  const [fechaVencimiento, setFechaVencimiento] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const factura = await api.certificaciones.generarFactura(certificacionId, {
        serie,
        fecha_vencimiento: fechaVencimiento || null,
      })
      onGenerada(factura.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title="Generar factura desde la certificación" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          La factura nace en borrador, sin número fiscal todavía. El número se asigna al
          emitirla, para no dejar huecos en la serie si se descarta.
        </p>
        <div className="form-grid">
          <Field label="Serie">
            <input className="input" value={serie} onChange={(e) => setSerie(e.target.value)} />
          </Field>
          <Field label="Fecha de vencimiento" hint="Opcional">
            <input
              className="input"
              type="date"
              value={fechaVencimiento}
              onChange={(e) => setFechaVencimiento(e.target.value)}
            />
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {guardando ? 'Generando…' : 'Generar factura'}
        </button>
      </div>
    </Modal>
  )
}
