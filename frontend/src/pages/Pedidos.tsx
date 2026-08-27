import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO_PEDIDO, api } from '../lib/api'
import type { ObraResumen, PedidoResumen, PresupuestoResumen, Tercero } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoPedidos = { onCambio: () => void }

export function useContextoPedidos() {
  return useOutletContext<ContextoPedidos>()
}

export function Pedidos() {
  const [items, setItems] = useState<PedidoResumen[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.pedidos.list({ limit: LIMITE })
      setItems(page.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const columnas = useMemo<ColumnaTabla<PedidoResumen>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (p) => p.codigo, anchoInicial: 110 },
      {
        id: 'proveedor',
        encabezado: 'Proveedor',
        accessor: (p) => p.proveedor_razon_social,
        render: (p) => (
          <Link className="table__link" to={`${p.id}`}>
            {p.proveedor_razon_social}
          </Link>
        ),
        anchoInicial: 260,
      },
      { id: 'fecha', encabezado: 'Fecha', accessor: (p) => p.fecha, tipo: 'fecha', anchoInicial: 140 },
      {
        id: 'estado',
        encabezado: 'Estado',
        accessor: (p) => p.estado,
        render: (p) => (
          <span className={`chip chip--estado-pedido-${p.estado}`}>
            {ETIQUETA_ESTADO_PEDIDO[p.estado]}
          </span>
        ),
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_ESTADO_PEDIDO).map(([value, label]) => ({ value, label })),
        anchoInicial: 150,
      },
      {
        id: 'total',
        encabezado: 'Total',
        accessor: (p) => p.total,
        render: (p) => <strong>{formatoImporte(p.total)}</strong>,
        tipo: 'importe',
        anchoInicial: 110,
      },
    ],
    [],
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Pedidos</h1>
          <p className="page-lead">
            Órdenes de compra en firme a proveedor — desde confirmar una oferta ganadora, o
            directas.
          </p>
        </div>
        <Tooltip texto="Crear un pedido a proveedor">
          <Link className="btn btn--primary" to="nuevo">
            <Plus size={16} aria-hidden="true" />
            Nuevo pedido
          </Link>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin pedidos">Registra el primero para empezar.</EmptyState>
      ) : (
        <DataTable
          id="pedidos"
          columnas={columnas}
          datos={items}
          claveFila={(p) => p.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoPedidos} />
    </>
  )
}

export function PedidoCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoPedidos()
  const [obras, setObras] = useState<ObraResumen[]>([])
  const [proveedores, setProveedores] = useState<Tercero[]>([])
  const [obraId, setObraId] = useState('')
  const [proveedorId, setProveedorId] = useState('')
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [fechaEntrega, setFechaEntrega] = useState('')
  const [ofertas, setOfertas] = useState<PresupuestoResumen[]>([])
  const [ofertaId, setOfertaId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    void Promise.all([
      api.obras.list({ limit: 200 }),
      api.terceros.list({ rol: 'proveedor', activo: true, limit: 500 }),
    ])
      .then(([obrasPage, provPage]) => {
        setObras(obrasPage.items)
        setProveedores(provPage.items)
        if (obrasPage.items.length > 0) setObraId(obrasPage.items[0].id)
        if (provPage.items.length > 0) setProveedorId(provPage.items[0].id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  // Ofertas ganadoras disponibles de este proveedor — para generar el
  // pedido confirmando una en vez de escribir las líneas a mano.
  useEffect(() => {
    setOfertaId('')
    if (!proveedorId) {
      setOfertas([])
      return
    }
    void api.presupuestos
      .list({ tipo: 'proveedor', limit: 200 })
      .then((page) => setOfertas(page.items.filter((p) => p.proveedor_id === proveedorId)))
      .catch(() => setOfertas([]))
  }, [proveedorId])

  function cerrar() {
    navigate('/pedidos')
  }

  async function guardar() {
    setError(null)
    setGuardando(true)
    try {
      const pedido = await api.pedidos.create({
        obra_id: obraId,
        proveedor_id: proveedorId,
        fecha,
        fecha_entrega_prevista: fechaEntrega || null,
        origen_oferta_presupuesto_id: ofertaId || null,
      })
      onCambio()
      navigate(`/pedidos/${pedido.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Nuevo pedido" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          {obras.length === 0 || proveedores.length === 0 ? (
            <EmptyState title="Hace falta una obra y un proveedor">
              Crea antes al menos una obra y marca algún tercero con el rol de proveedor.
            </EmptyState>
          ) : (
            <>
              <div className="form-grid">
                <Field label="Obra">
                  <select className="select" value={obraId} onChange={(e) => setObraId(e.target.value)}>
                    {obras.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.codigo} · {o.nombre}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Proveedor">
                  <select
                    className="select"
                    value={proveedorId}
                    onChange={(e) => setProveedorId(e.target.value)}
                  >
                    {proveedores.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.razon_social}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Fecha">
                  <input
                    className="input"
                    type="date"
                    value={fecha}
                    onChange={(e) => setFecha(e.target.value)}
                  />
                </Field>
                <Field label="Entrega prevista" hint="Opcional">
                  <input
                    className="input"
                    type="date"
                    value={fechaEntrega}
                    onChange={(e) => setFechaEntrega(e.target.value)}
                  />
                </Field>
              </div>
              <div style={{ marginTop: 'var(--sp-4)' }}>
                <Field
                  label="Generar desde una oferta ganadora"
                  hint={
                    ofertas.length === 0
                      ? 'Este proveedor no tiene ofertas resueltas — se creará vacío, añade las líneas después'
                      : 'Copia sus partidas como líneas del pedido; déjalo en blanco para añadirlas a mano'
                  }
                >
                  <select
                    className="select"
                    value={ofertaId}
                    onChange={(e) => setOfertaId(e.target.value)}
                    disabled={ofertas.length === 0}
                  >
                    <option value="">— Sin oferta, líneas a mano —</option>
                    {ofertas.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.codigo} · {o.nombre}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
            </>
          )}
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={obraId === '' || proveedorId === '' || guardando}
            onClick={() => void guardar()}
          >
            <Plus size={16} aria-hidden="true" />
            {guardando ? 'Creando…' : 'Crear'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
