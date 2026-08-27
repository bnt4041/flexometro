import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FileDown, Plus, Send, Trash2, X } from 'lucide-react'

import { ContactosAsociados } from '../components/ContactosAsociados'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { Trazabilidad, cargarAsociadosDeObra } from '../components/Trazabilidad'
import { ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { WidgetGrid } from '../components/WidgetGrid'
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

  const pestanaDatos = (
    <>
      <ErrorNotice error={error} />

      <WidgetGrid
        id="certificacion-datos"
        widgets={[
          {
            id: 'lineas',
            titulo: 'Líneas certificadas',
            x: 0,
            y: 0,
            w: 8,
            h: 12,
            minW: 4,
            minH: 6,
            contenido: (
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
            ),
          },
          {
            id: 'resumen',
            titulo: 'Resumen',
            x: 8,
            y: 0,
            w: 4,
            h: 12,
            minW: 3,
            minH: 6,
            contenido: (
              <div className="resumen-totales">
                <div className="resumen-totales__fila">
                  <span>Importe ejecutado en este periodo</span>
                  <span className="resumen-totales__valor">
                    {formatoImporte(certificacion.importe_ejecutado)} €
                  </span>
                </div>
                {Number(certificacion.retencion_garantia_pct) > 0 && (
                  <div className="resumen-totales__fila is-suave">
                    <span>
                      Retención de garantía ({formatoImporte(certificacion.retencion_garantia_pct)} %)
                    </span>
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
            ),
          },
        ]}
      />

      <div className="card" style={{ marginTop: 'var(--sp-4)' }}>
        <div className="form-actions form-actions--separadas">
          {esBorrador ? (
            <Tooltip texto="Eliminar esta certificación">
              <button className="btn btn--danger" onClick={() => void eliminar()}>
                <Trash2 size={16} aria-hidden="true" />
                Eliminar
              </button>
            </Tooltip>
          ) : (
            <span />
          )}
          <span className="form-actions__grupo">
            <Tooltip texto="Descargar el PDF de esta certificación">
              <button
                className="btn"
                onClick={() =>
                  void descargar(api.certificaciones.pdfUrl(id), `${certificacion!.codigo}.pdf`, {
                    abrir: true,
                  }).catch((err) => setError(err instanceof Error ? err.message : String(err)))
                }
              >
                <FileDown size={16} aria-hidden="true" />
                PDF
              </button>
            </Tooltip>
            {esBorrador ? (
              <Tooltip texto="Emitir: a partir de aquí queda bloqueada">
                <button className="btn btn--primary" onClick={() => void emitir()}>
                  <Send size={16} aria-hidden="true" />
                  Emitir
                </button>
              </Tooltip>
            ) : (
              !certificacion!.facturada && (
                <Tooltip texto="Generar la factura a partir de esta certificación">
                  <button className="btn btn--primary" onClick={() => setGenerando(true)}>
                    <Plus size={16} aria-hidden="true" />
                    Generar factura
                  </button>
                </Tooltip>
              )
            )}
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
    </>
  )

  const pestanas: PestanaFicha[] = [
    { id: 'datos', etiqueta: 'Datos', icono: 'datos', contenido: pestanaDatos },
    {
      id: 'contactos',
      etiqueta: 'Contactos',
      icono: 'contactos',
      contenido: <ContactosAsociados entidad="certificacion" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="certificacion" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="certificacion" entidadId={id} />,
    },
    {
      id: 'trazabilidad',
      etiqueta: 'Trazabilidad',
      icono: 'trazabilidad',
      contenido: (
        <Trazabilidad
          origen={[]}
          cargarAsociados={() =>
            cargarAsociadosDeObra(certificacion.obra_id, { tipo: 'certificacion', id })
          }
        />
      ),
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.certificaciones.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          Certificación nº {certificacion.numero}{' '}
          <span className="table__code">{certificacion.codigo}</span>
        </>
      }
      subtitulo={
        <p className="page-lead" style={{ marginBottom: 0 }}>
          {obra && <>Obra <Link to={`/obras/${obra.id}`}>{obra.codigo}</Link> · </>}
          {certificacion.fecha}{' '}
          <span className={`chip chip--estado-cert-${certificacion.estado}`}>
            {ETIQUETA_ESTADO_CERTIFICACION[certificacion.estado]}
          </span>
          {certificacion.facturada && <span className="badge"> facturada</span>}
        </p>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
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
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {!guardando && <Plus size={16} aria-hidden="true" />}
          {guardando ? 'Generando…' : 'Generar factura'}
        </button>
      </div>
    </Modal>
  )
}
