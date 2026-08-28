import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Plus, Trash2, X } from 'lucide-react'

import { ContactosAsociados } from '../components/ContactosAsociados'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { Trazabilidad, cargarAsociadosDeObra } from '../components/Trazabilidad'
import {
  EmptyState,
  ErrorNotice,
  Field,
  Modal,
  ModalPantalla,
  Tooltip,
  formatoImporte,
} from '../components/ui'
import { ETIQUETA_ESTADO_PEDIDO, ETIQUETA_TIPO_PEDIDO, api } from '../lib/api'
import type {
  Concepto,
  EstadoPedido,
  PedidoDetalle as Detalle,
} from '../lib/api'
import { useContextoPedidos } from './Pedidos'

export function PedidoDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoPedidos()
  const [pedido, setPedido] = useState<Detalle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [anadiendo, setAnadiendo] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setPedido(await api.pedidos.get(id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/pedidos')
  }

  if (error && !pedido) {
    return (
      <ModalPantalla title="Pedido" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!pedido) return null

  async function cambiarEstado(estado: EstadoPedido) {
    try {
      await api.pedidos.update(id, { estado })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar el pedido ${pedido!.codigo}?`)) return
    try {
      await api.pedidos.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminarLinea(lineaId: string) {
    await api.pedidosLineas.remove(lineaId)
    await cargar()
  }

  const pestanaDatos = (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          {pedido.fecha}
          {pedido.fecha_entrega_prevista && <> · entrega prevista {pedido.fecha_entrega_prevista}</>}
          {pedido.origen_oferta_presupuesto_id && (
            <>
              {' '}
              ·{' '}
              <Link to={`/presupuestos/${pedido.origen_oferta_presupuesto_id}`}>
                {pedido.tipo === 'proveedor' ? 'desde oferta' : 'desde presupuesto'}
              </Link>
            </>
          )}
        </p>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <select
            className="select"
            style={{ width: 'auto' }}
            value={pedido.estado}
            onChange={(e) => void cambiarEstado(e.target.value as EstadoPedido)}
          >
            {Object.entries(ETIQUETA_ESTADO_PEDIDO).map(([clave, etiqueta]) => (
              <option key={clave} value={clave}>
                {etiqueta}
              </option>
            ))}
          </select>
          <Tooltip texto="Eliminar este pedido">
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
        {pedido.lineas.length === 0 ? (
          <EmptyState title="Sin líneas">
            Añade lo que se encarga {pedido.tipo === 'proveedor' ? 'al proveedor' : 'del cliente'}.
          </EmptyState>
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
              {pedido.lineas.map((l) => (
                <tr key={l.id}>
                  <td>
                    {l.descripcion} <span className="muted">({l.unidad})</span>
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
                  <strong>{formatoImporte(pedido.total)}</strong>
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        )}
      </div>

      {anadiendo && (
        <NuevaLineaModal
          pedidoId={id}
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
      contenido: <ContactosAsociados entidad="pedido" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="pedido" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="pedido" entidadId={id} />,
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
              etiqueta: pedido.tercero_razon_social,
              ruta: `/terceros/${pedido.cliente_id ?? pedido.proveedor_id}`,
              estadoEtiqueta: ETIQUETA_TIPO_PEDIDO[pedido.tipo],
            },
            ...(pedido.origen_oferta_presupuesto_id
              ? [
                  {
                    tipo: 'presupuesto' as const,
                    etiqueta: pedido.tipo === 'proveedor' ? 'Oferta ganadora' : 'Presupuesto de origen',
                    ruta: `/presupuestos/${pedido.origen_oferta_presupuesto_id}`,
                  },
                ]
              : []),
          ]}
          cargarAsociados={() =>
            cargarAsociadosDeObra(pedido.obra_id, { tipo: 'pedido', id })
          }
        />
      ),
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.pedidos.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {pedido.tercero_razon_social} <span className="table__code">{pedido.codigo}</span>
        </>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}

function NuevaLineaModal({
  pedidoId,
  onClose,
  onAnadida,
}: {
  pedidoId: string
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
    const idTimeout = setTimeout(() => {
      void api.conceptos
        .list({ q: q || undefined, activo: true, limit: 50 })
        .then((page) => setConceptos(page.items))
        .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
    }, 250)
    return () => clearTimeout(idTimeout)
  }, [q, modo])

  async function guardar() {
    setError(null)
    try {
      await api.pedidos.addLinea(
        pedidoId,
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
