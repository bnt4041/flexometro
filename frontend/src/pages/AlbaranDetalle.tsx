import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Plus, Trash2, X } from 'lucide-react'

import { ContactosAsociados } from '../components/ContactosAsociados'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { Trazabilidad, cargarAsociadosDeObra } from '../components/Trazabilidad'
import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { ETIQUETA_ESTADO_ALBARAN, api } from '../lib/api'
import type {
  AlbaranDetalle as Detalle,
  Concepto,
  EstadoAlbaran,
} from '../lib/api'
import { useContextoAlbaranes } from './Albaranes'

export function AlbaranDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoAlbaranes()
  const [albaran, setAlbaran] = useState<Detalle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [anadiendo, setAnadiendo] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setAlbaran(await api.albaranes.get(id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/albaranes')
  }

  if (error && !albaran) {
    return (
      <ModalPantalla title="Albarán" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!albaran) return null

  async function cambiarEstado(estado: EstadoAlbaran) {
    try {
      await api.albaranes.update(id, { estado })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar el albarán ${albaran!.codigo}?`)) return
    try {
      await api.albaranes.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminarLinea(lineaId: string) {
    await api.albaranesLineas.remove(lineaId)
    await cargar()
  }

  const pestanaDatos = (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          {albaran.numero_proveedor && <>Nº proveedor {albaran.numero_proveedor} · </>}
          {albaran.fecha}
        </p>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <select
            className="select"
            style={{ width: 'auto' }}
            value={albaran.estado}
            onChange={(e) => void cambiarEstado(e.target.value as EstadoAlbaran)}
          >
            {Object.entries(ETIQUETA_ESTADO_ALBARAN).map(([clave, etiqueta]) => (
              <option key={clave} value={clave}>
                {etiqueta}
              </option>
            ))}
          </select>
          <Tooltip texto="Eliminar este albarán">
            <button className="btn btn--danger" onClick={() => void eliminar()}>
              <Trash2 size={16} aria-hidden="true" />
              Eliminar
            </button>
          </Tooltip>
        </div>
      </div>

      <ErrorNotice error={error} />

      <div className="page-head" style={{ marginBottom: 'var(--sp-3)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Líneas</h2>
        <button className="btn" onClick={() => setAnadiendo(true)}>
          <Plus size={16} aria-hidden="true" />
          Añadir línea
        </button>
      </div>

      <div className="table-wrap">
        {albaran.lineas.length === 0 ? (
          <EmptyState title="Sin líneas">Añade el material recibido.</EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Descripción</th>
                <th className="table__num">Cantidad</th>
                <th className="table__num">Precio</th>
                <th className="table__num">Importe</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {albaran.lineas.map((l) => (
                <tr key={l.id}>
                  <td>
                    {l.descripcion} <span className="muted">({l.unidad})</span>
                    {l.capitulo_id && <div className="muted">imputado a capítulo</div>}
                  </td>
                  <td className="table__num">{formatoImporte(l.cantidad, 3)}</td>
                  <td className="table__num">{formatoImporte(l.precio_unitario, 4)}</td>
                  <td className="table__num">
                    <strong>{formatoImporte(l.importe)}</strong>
                  </td>
                  <td className="table__actions">
                    <Tooltip texto="Quitar esta línea">
                      <button
                        className="btn btn--sm btn--danger btn--solo-icono"
                        onClick={() => void eliminarLinea(l.id)}
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
                <td colSpan={3} className="table__num total-label">
                  Total
                </td>
                <td className="table__num">
                  <strong>{formatoImporte(albaran.total)}</strong>
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        )}
      </div>

      {anadiendo && (
        <NuevaLineaModal
          albaranId={id}
          onClose={() => setAnadiendo(false)}
          onAnadida={() => {
            setAnadiendo(false)
            void cargar()
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
      contenido: <ContactosAsociados entidad="albaran" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="albaran" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="albaran" entidadId={id} />,
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
              etiqueta: albaran.proveedor_razon_social,
              ruta: `/terceros/${albaran.proveedor_id}`,
              estadoEtiqueta: 'Proveedor',
            },
            ...(albaran.pedido_id
              ? [
                  {
                    tipo: 'pedido' as const,
                    etiqueta: 'Pedido de origen',
                    ruta: `/pedidos/${albaran.pedido_id}`,
                  },
                ]
              : []),
          ]}
          cargarAsociados={() =>
            cargarAsociadosDeObra(albaran.obra_id, { tipo: 'albaran', id })
          }
        />
      ),
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.albaranes.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {albaran.proveedor_razon_social} <span className="table__code">{albaran.codigo}</span>
        </>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}

function NuevaLineaModal({
  albaranId,
  onClose,
  onAnadida,
}: {
  albaranId: string
  onClose: () => void
  onAnadida: () => void
}) {
  const [modo, setModo] = useState<'banco' | 'manual'>('banco')
  const [q, setQ] = useState('')
  const [conceptos, setConceptos] = useState<Concepto[]>([])
  const [conceptoId, setConceptoId] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [unidad, setUnidad] = useState('ud')
  const [cantidad, setCantidad] = useState('1')
  const [precio, setPrecio] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (modo !== 'banco') return
    const id = setTimeout(() => {
      void api.conceptos
        .list({ q: q || undefined, activo: true, limit: 50 })
        .then((page) => setConceptos(page.items))
        .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
    }, 250)
    return () => clearTimeout(id)
  }, [q, modo])

  async function guardar() {
    setError(null)
    try {
      await api.albaranes.addLinea(
        albaranId,
        modo === 'banco'
          ? { concepto_id: conceptoId, cantidad, precio_unitario: precio || null }
          : { descripcion, unidad, cantidad, precio_unitario: precio },
      )
      onAnadida()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const listo =
    modo === 'banco'
      ? conceptoId !== '' && cantidad !== ''
      : descripcion.trim() !== '' && cantidad !== '' && precio !== ''

  return (
    <Modal title="Añadir línea" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Origen">
          <select
            className="select"
            value={modo}
            onChange={(e) => setModo(e.target.value as 'banco' | 'manual')}
          >
            <option value="banco">Del banco de precios</option>
            <option value="manual">Descripción manual</option>
          </select>
        </Field>

        {modo === 'banco' ? (
          <>
            <div style={{ marginTop: 'var(--sp-4)' }}>
              <Field label="Buscar en el banco de precios">
                <input
                  className="input"
                  placeholder="Código o descripción…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  autoFocus
                />
              </Field>
            </div>
            <div className="lista-seleccion">
              {conceptos.length === 0 ? (
                <div className="muted" style={{ padding: 'var(--sp-3)' }}>
                  Sin resultados
                </div>
              ) : (
                conceptos.map((c) => (
                  <button
                    key={c.id}
                    className={
                      conceptoId === c.id ? 'lista-seleccion__item is-activo' : 'lista-seleccion__item'
                    }
                    onClick={() => setConceptoId(c.id)}
                  >
                    <span className="table__code">{c.codigo}</span>
                    <span className="lista-seleccion__texto">{c.resumen}</span>
                    <span className="table__num">{c.unidad}</span>
                  </button>
                ))
              )}
            </div>
          </>
        ) : (
          <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
            <Field ancho="doble" label="Descripción">
              <input
                className="input"
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
              />
            </Field>
            <Field label="Unidad">
              <input className="input" value={unidad} onChange={(e) => setUnidad(e.target.value)} />
            </Field>
          </div>
        )}

        <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
          <Field label="Cantidad">
            <input
              className="input"
              type="number"
              step="0.001"
              value={cantidad}
              onChange={(e) => setCantidad(e.target.value)}
            />
          </Field>
          <Field
            label="Precio unitario"
            hint={modo === 'banco' ? 'Vacío: tarifa del proveedor' : undefined}
          >
            <input
              className="input"
              type="number"
              step="0.0001"
              value={precio}
              onChange={(e) => setPrecio(e.target.value)}
            />
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={!listo} onClick={() => void guardar()}>
          <Plus size={16} aria-hidden="true" />
          Añadir
        </button>
      </div>
    </Modal>
  )
}
