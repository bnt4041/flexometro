import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO_PEDIDO, ETIQUETA_TIPO_PEDIDO, api } from '../lib/api'
import type { ObraResumen, PedidoResumen, PresupuestoResumen, Tercero, TipoPedido } from '../lib/api'

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
        id: 'tipo',
        encabezado: 'Tipo',
        accessor: (p) => p.tipo,
        render: (p) => ETIQUETA_TIPO_PEDIDO[p.tipo],
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_TIPO_PEDIDO).map(([value, label]) => ({ value, label })),
        anchoInicial: 100,
      },
      {
        id: 'tercero',
        encabezado: 'Cliente / proveedor',
        accessor: (p) => p.tercero_razon_social,
        render: (p) => (
          <Link className="table__link" to={`${p.id}`}>
            {p.tercero_razon_social}
          </Link>
        ),
        anchoInicial: 240,
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
            Lo que se encarga en firme — a un proveedor (orden de compra) o de un cliente.
          </p>
        </div>
        <Tooltip texto="Crear un pedido">
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
  const [tipo, setTipo] = useState<TipoPedido>('proveedor')
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [obraId, setObraId] = useState('')
  const [terceroId, setTerceroId] = useState('')
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [fechaEntrega, setFechaEntrega] = useState('')
  const [presupuestos, setPresupuestos] = useState<PresupuestoResumen[]>([])
  const [presupuestoId, setPresupuestoId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    void api.obras
      .list({ limit: 200 })
      .then((page) => {
        setObras(page.items)
        if (page.items.length > 0) setObraId(page.items[0].id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  useEffect(() => {
    setTerceroId('')
    void api.terceros
      .list({ rol: tipo, activo: true, limit: 500 })
      .then((page) => {
        setTerceros(page.items)
        if (page.items.length > 0) setTerceroId(page.items[0].id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [tipo])

  // De proveedor: sus ofertas ganadoras (presupuestos tipo=proveedor), para
  // generar el pedido confirmando una en vez de escribir las líneas a mano.
  // De cliente: sus presupuestos aprobados, por si el pedido viene de uno ya
  // cerrado — mismo mecanismo, el otro lado del negocio.
  useEffect(() => {
    setPresupuestoId('')
    if (!terceroId) {
      setPresupuestos([])
      return
    }
    void api.presupuestos
      .list({ tipo, limit: 200 })
      .then((page) => {
        const campo = tipo === 'proveedor' ? 'proveedor_id' : 'cliente_id'
        setPresupuestos(page.items.filter((p) => p[campo] === terceroId))
      })
      .catch(() => setPresupuestos([]))
  }, [tipo, terceroId])

  function cerrar() {
    navigate('/pedidos')
  }

  async function guardar() {
    setError(null)
    setGuardando(true)
    try {
      const pedido = await api.pedidos.create({
        tipo,
        obra_id: obraId,
        proveedor_id: tipo === 'proveedor' ? terceroId : null,
        cliente_id: tipo === 'cliente' ? terceroId : null,
        fecha,
        fecha_entrega_prevista: fechaEntrega || null,
        origen_oferta_presupuesto_id: presupuestoId || null,
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
          {obras.length === 0 ? (
            <EmptyState title="Hace falta una obra">Crea antes al menos una obra.</EmptyState>
          ) : (
            <>
              <div className="form-grid">
                <Field label="Tipo">
                  <select
                    className="select"
                    value={tipo}
                    onChange={(e) => setTipo(e.target.value as TipoPedido)}
                  >
                    <option value="proveedor">A un proveedor</option>
                    <option value="cliente">De un cliente</option>
                  </select>
                </Field>
                <Field label="Obra">
                  <select className="select" value={obraId} onChange={(e) => setObraId(e.target.value)}>
                    {obras.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.codigo} · {o.nombre}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label={tipo === 'proveedor' ? 'Proveedor' : 'Cliente'}>
                  {terceros.length === 0 ? (
                    <p className="muted">
                      No hay ningún tercero con el rol de {tipo === 'proveedor' ? 'proveedor' : 'cliente'}
                    </p>
                  ) : (
                    <select
                      className="select"
                      value={terceroId}
                      onChange={(e) => setTerceroId(e.target.value)}
                    >
                      {terceros.map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.razon_social}
                        </option>
                      ))}
                    </select>
                  )}
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
                  label={
                    tipo === 'proveedor' ? 'Generar desde una oferta ganadora' : 'Generar desde un presupuesto'
                  }
                  hint={
                    presupuestos.length === 0
                      ? 'No hay ninguno disponible — se creará vacío, añade las líneas después'
                      : 'Copia sus partidas como líneas del pedido; déjalo en blanco para añadirlas a mano'
                  }
                >
                  <select
                    className="select"
                    value={presupuestoId}
                    onChange={(e) => setPresupuestoId(e.target.value)}
                    disabled={presupuestos.length === 0}
                  >
                    <option value="">— Sin presupuesto, líneas a mano —</option>
                    {presupuestos.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.codigo} · {p.nombre}
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
            disabled={obraId === '' || terceroId === '' || guardando}
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
