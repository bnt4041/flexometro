import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Save, Trash2, X } from 'lucide-react'

import { ContactosAsociados } from '../components/ContactosAsociados'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { Trazabilidad, cargarAsociadosDeObra } from '../components/Trazabilidad'
import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { ETIQUETA_ESTADO_FACTURA_RECIBIDA, ETIQUETA_IVA, api } from '../lib/api'
import type { AlbaranResumen, EstadoFacturaRecibida, FacturaRecibida as Detalle, TipoIVA } from '../lib/api'
import { useContextoFacturasRecibidas } from './FacturasRecibidas'

export function FacturaRecibidaDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoFacturasRecibidas()
  const [factura, setFactura] = useState<Detalle | null>(null)
  const [borrador, setBorrador] = useState<Partial<Detalle>>({})
  const [albaranesObra, setAlbaranesObra] = useState<AlbaranResumen[]>([])
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const f = await api.facturasRecibidas.get(id)
      setFactura(f)
      const page = await api.albaranes.list({ obra_id: f.obra_id, proveedor_id: f.proveedor_id, limit: 200 })
      setAlbaranesObra(page.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/facturas-recibidas')
  }

  if (error && !factura) {
    return (
      <ModalPantalla title="Factura recibida" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!factura) return null

  const valor = <K extends keyof Detalle>(campo: K): Detalle[K] =>
    (borrador[campo] ?? factura[campo]) as Detalle[K]
  const cambiar = <K extends keyof Detalle>(campo: K, v: Detalle[K]) =>
    setBorrador((b) => ({ ...b, [campo]: v }))
  const hayCambios = Object.keys(borrador).length > 0

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.facturasRecibidas.update(id, borrador)
      setBorrador({})
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar la factura ${factura!.codigo}?`)) return
    try {
      await api.facturasRecibidas.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function quitarAlbaran(albaranId: string) {
    try {
      await api.facturasRecibidas.update(id, {
        albaran_ids: factura!.albaran_ids.filter((a) => a !== albaranId),
      })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function anadirAlbaran(albaranId: string) {
    if (!albaranId) return
    try {
      await api.facturasRecibidas.update(id, {
        albaran_ids: [...factura!.albaran_ids, albaranId],
      })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const disponibles = albaranesObra.filter((a) => !factura.albaran_ids.includes(a.id))

  const pestanaDatos = (
    <div className="ficha-datos">
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <div className="form-grid">
            <Field label="Obra">
              <Link to={`/obras/${factura.obra_id}`}>Ver obra</Link>
            </Field>
            <Field label="Proveedor">
              <span>{factura.proveedor_razon_social}</span>
            </Field>
            <Field label="Estado">
              <select
                className="select"
                value={valor('estado')}
                onChange={(e) => cambiar('estado', e.target.value as EstadoFacturaRecibida)}
              >
                {Object.entries(ETIQUETA_ESTADO_FACTURA_RECIBIDA).map(([clave, etiqueta]) => (
                  <option key={clave} value={clave}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Nº de factura">
              <input
                className="input"
                value={valor('numero_proveedor')}
                onChange={(e) => cambiar('numero_proveedor', e.target.value)}
              />
            </Field>
            <Field label="Fecha">
              <input
                className="input"
                type="date"
                value={valor('fecha')}
                onChange={(e) => cambiar('fecha', e.target.value)}
              />
            </Field>
            <Field label="Vencimiento">
              <input
                className="input"
                type="date"
                value={valor('fecha_vencimiento') ?? ''}
                onChange={(e) => cambiar('fecha_vencimiento', e.target.value || null)}
              />
            </Field>
            <Field label="Base imponible">
              <input
                className="input"
                inputMode="decimal"
                value={valor('base_imponible')}
                onChange={(e) => cambiar('base_imponible', e.target.value)}
              />
            </Field>
            <Field label="IVA">
              <select
                className="select"
                value={valor('tipo_iva')}
                onChange={(e) => cambiar('tipo_iva', e.target.value as TipoIVA)}
              >
                {(Object.keys(ETIQUETA_IVA) as TipoIVA[]).map((t) => (
                  <option key={t} value={t}>
                    {ETIQUETA_IVA[t]}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Total">
              <strong>{formatoImporte(factura.total)}</strong>
            </Field>
          </div>
          <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
            <Field ancho="doble" label="Notas">
              <textarea
                className="input"
                rows={3}
                value={valor('notas') ?? ''}
                onChange={(e) => cambiar('notas', e.target.value || null)}
              />
            </Field>
          </div>
        </div>

        <div className="form-actions form-actions--separadas">
          <Tooltip texto="Eliminar esta factura">
            <button className="btn btn--danger" onClick={() => void eliminar()}>
              <Trash2 size={16} aria-hidden="true" />
              Eliminar
            </button>
          </Tooltip>
          <span className="form-actions__grupo">
            <button className="btn" disabled={!hayCambios} onClick={() => setBorrador({})}>
              <X size={16} aria-hidden="true" />
              Descartar
            </button>
            <button
              className="btn btn--primary"
              disabled={!hayCambios || guardando}
              onClick={() => void guardar()}
            >
              {!guardando && <Save size={16} aria-hidden="true" />}
              {guardando ? 'Guardando…' : 'Guardar cambios'}
            </button>
          </span>
        </div>
      </div>

      <div className="page-head" style={{ marginTop: 'var(--sp-5)', marginBottom: 'var(--sp-3)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Albaranes que cubre</h2>
        {disponibles.length > 0 && (
          <select className="select" style={{ width: 'auto' }} value="" onChange={(e) => void anadirAlbaran(e.target.value)}>
            <option value="">+ Añadir albarán…</option>
            {disponibles.map((a) => (
              <option key={a.id} value={a.id}>
                {a.codigo} · {formatoImporte(a.total)} €
              </option>
            ))}
          </select>
        )}
      </div>

      {factura.albaran_ids.length === 0 ? (
        <EmptyState title="Sin albaranes asociados">
          El cuadre entre lo entregado y lo facturado necesita saber qué albaranes cubre.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Albarán</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {factura.albaran_ids.map((aid, i) => (
                <tr key={aid}>
                  <td>
                    <Link to={`/albaranes/${aid}`}>{factura.albaran_codigos[i] ?? aid}</Link>
                  </td>
                  <td className="table__actions">
                    <Tooltip texto="Quitar de esta factura">
                      <button
                        className="btn btn--sm btn--danger btn--solo-icono"
                        onClick={() => void quitarAlbaran(aid)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </Tooltip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )

  const pestanas: PestanaFicha[] = [
    { id: 'datos', etiqueta: 'Datos', icono: 'datos', contenido: pestanaDatos },
    {
      id: 'contactos',
      etiqueta: 'Contactos',
      icono: 'contactos',
      contenido: <ContactosAsociados entidad="factura_recibida" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="factura_recibida" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="factura_recibida" entidadId={id} />,
    },
    {
      id: 'trazabilidad',
      etiqueta: 'Trazabilidad',
      icono: 'trazabilidad',
      contenido: (
        <Trazabilidad
          origen={[
            {
              tipo: 'tercero',
              etiqueta: factura.proveedor_razon_social,
              ruta: `/terceros/${factura.proveedor_id}`,
              estadoEtiqueta: 'Proveedor',
            },
            ...factura.albaran_ids.map((aid, i) => ({
              tipo: 'albaran' as const,
              etiqueta: factura.albaran_codigos[i] ?? aid,
              ruta: `/albaranes/${aid}`,
            })),
          ]}
          cargarAsociados={() =>
            cargarAsociadosDeObra(factura.obra_id, { tipo: 'factura-recibida', id })
          }
        />
      ),
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.facturasRecibidas.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {factura.proveedor_razon_social} <span className="table__code">{factura.codigo}</span>
        </>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}
