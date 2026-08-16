import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, formatoImporte } from '../components/ui'
import { ETIQUETA_ESTADO_ALBARAN, api } from '../lib/api'
import type {
  AlbaranDetalle as Detalle,
  EstadoAlbaran,
  Producto,
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

  return (
    <ModalPantalla
      title={
        <>
          {albaran.proveedor_razon_social} <span className="table__code">{albaran.codigo}</span>
        </>
      }
      onClose={cerrar}
    >
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
          <button className="btn btn--danger" onClick={() => void eliminar()}>
            Eliminar
          </button>
        </div>
      </div>

      <ErrorNotice error={error} />

      <div className="page-head" style={{ marginBottom: 'var(--sp-3)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Líneas</h2>
        <button className="btn" onClick={() => setAnadiendo(true)}>
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
                    <button
                      className="btn btn--sm btn--danger"
                      onClick={() => void eliminarLinea(l.id)}
                    >
                      ×
                    </button>
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
    </ModalPantalla>
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
  const [modo, setModo] = useState<'catalogo' | 'manual'>('catalogo')
  const [q, setQ] = useState('')
  const [productos, setProductos] = useState<Producto[]>([])
  const [productoId, setProductoId] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [unidad, setUnidad] = useState('ud')
  const [cantidad, setCantidad] = useState('1')
  const [precio, setPrecio] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (modo !== 'catalogo') return
    const id = setTimeout(() => {
      void api.productos
        .list({ q: q || undefined, activo: true, limit: 50 })
        .then((page) => setProductos(page.items))
        .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
    }, 250)
    return () => clearTimeout(id)
  }, [q, modo])

  async function guardar() {
    setError(null)
    try {
      await api.albaranes.addLinea(
        albaranId,
        modo === 'catalogo'
          ? { producto_id: productoId, cantidad, precio_unitario: precio || null }
          : { descripcion, unidad, cantidad, precio_unitario: precio },
      )
      onAnadida()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const listo =
    modo === 'catalogo'
      ? productoId !== '' && cantidad !== ''
      : descripcion.trim() !== '' && cantidad !== '' && precio !== ''

  return (
    <Modal title="Añadir línea" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Origen">
          <select
            className="select"
            value={modo}
            onChange={(e) => setModo(e.target.value as 'catalogo' | 'manual')}
          >
            <option value="catalogo">Producto del catálogo</option>
            <option value="manual">Descripción manual</option>
          </select>
        </Field>

        {modo === 'catalogo' ? (
          <>
            <div style={{ marginTop: 'var(--sp-4)' }}>
              <Field label="Buscar producto">
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
              {productos.length === 0 ? (
                <div className="muted" style={{ padding: 'var(--sp-3)' }}>
                  Sin resultados
                </div>
              ) : (
                productos.map((p) => (
                  <button
                    key={p.id}
                    className={
                      productoId === p.id ? 'lista-seleccion__item is-activo' : 'lista-seleccion__item'
                    }
                    onClick={() => setProductoId(p.id)}
                  >
                    <span className="table__code">{p.codigo}</span>
                    <span className="lista-seleccion__texto">{p.resumen}</span>
                    <span className="table__num">{p.unidad}</span>
                  </button>
                ))
              )}
            </div>
          </>
        ) : (
          <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
            <Field label="Descripción">
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
            hint={modo === 'catalogo' ? 'Vacío: tarifa del proveedor' : undefined}
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
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={!listo} onClick={() => void guardar()}>
          Añadir
        </button>
      </div>
    </Modal>
  )
}
