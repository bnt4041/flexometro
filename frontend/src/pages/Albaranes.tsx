import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO_ALBARAN, ETIQUETA_TIPO_ALBARAN, api } from '../lib/api'
import type { AlbaranResumen, ObraResumen, PedidoResumen, Tercero, TipoAlbaran } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoAlbaranes = { onCambio: () => void }

export function useContextoAlbaranes() {
  return useOutletContext<ContextoAlbaranes>()
}

export function Albaranes() {
  const [items, setItems] = useState<AlbaranResumen[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.albaranes.list({ limit: LIMITE })
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

  const columnas = useMemo<ColumnaTabla<AlbaranResumen>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (a) => a.codigo, anchoInicial: 110 },
      {
        id: 'tipo',
        encabezado: 'Tipo',
        accessor: (a) => a.tipo,
        render: (a) => ETIQUETA_TIPO_ALBARAN[a.tipo],
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_TIPO_ALBARAN).map(([value, label]) => ({ value, label })),
        anchoInicial: 100,
      },
      {
        id: 'tercero',
        encabezado: 'Cliente / proveedor',
        accessor: (a) => `${a.tercero_razon_social} ${a.numero_proveedor ?? ''}`,
        render: (a) => (
          <>
            <Link className="table__link" to={`${a.id}`}>
              {a.tercero_razon_social}
            </Link>
            {a.numero_proveedor && <div className="muted">Nº {a.numero_proveedor}</div>}
          </>
        ),
        anchoInicial: 260,
      },
      { id: 'fecha', encabezado: 'Fecha', accessor: (a) => a.fecha, tipo: 'fecha', anchoInicial: 160 },
      {
        id: 'estado',
        encabezado: 'Estado',
        accessor: (a) => a.estado,
        render: (a) => <span className={`chip chip--estado-${a.estado}`}>{ETIQUETA_ESTADO_ALBARAN[a.estado]}</span>,
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_ESTADO_ALBARAN).map(([value, label]) => ({ value, label })),
        anchoInicial: 140,
      },
      {
        id: 'total',
        encabezado: 'Total',
        accessor: (a) => a.total,
        render: (a) => <strong>{formatoImporte(a.total)}</strong>,
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
          <h1 className="page-title">Albaranes</h1>
          <p className="page-lead">
            Material recibido en obra desde un proveedor, o entregado/ejecutado a un cliente.
          </p>
        </div>
        <Tooltip texto="Registrar un albarán">
          <Link className="btn btn--primary" to="nuevo">
            <Plus size={16} aria-hidden="true" />
            Nuevo albarán
          </Link>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin albaranes">Registra el primero para empezar.</EmptyState>
      ) : (
        <DataTable
          id="albaranes"
          columnas={columnas}
          datos={items}
          claveFila={(a) => a.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoAlbaranes} />
    </>
  )
}

export function AlbaranCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoAlbaranes()
  const [obras, setObras] = useState<ObraResumen[]>([])
  const [tipo, setTipo] = useState<TipoAlbaran>('proveedor')
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [obraId, setObraId] = useState('')
  const [terceroId, setTerceroId] = useState('')
  const [numeroProveedor, setNumeroProveedor] = useState('')
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [pedidos, setPedidos] = useState<PedidoResumen[]>([])
  const [pedidoId, setPedidoId] = useState('')
  const [error, setError] = useState<string | null>(null)

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

  // Pedidos de este proveedor y obra, para poder decir de cuál viene esta
  // entrega — opcional, se sigue pudiendo dar de alta un albarán directo.
  // Solo aplica a proveedor: un albarán de cliente no cuelga de un pedido.
  useEffect(() => {
    setPedidoId('')
    if (tipo !== 'proveedor' || !obraId || !terceroId) {
      setPedidos([])
      return
    }
    void api.pedidos
      .list({ obra_id: obraId, proveedor_id: terceroId, limit: 100 })
      .then((page) => setPedidos(page.items))
      .catch(() => setPedidos([]))
  }, [tipo, obraId, terceroId])

  function cerrar() {
    navigate('/albaranes')
  }

  async function guardar() {
    setError(null)
    try {
      const albaran = await api.albaranes.create({
        tipo,
        obra_id: obraId,
        proveedor_id: tipo === 'proveedor' ? terceroId : null,
        cliente_id: tipo === 'cliente' ? terceroId : null,
        numero_proveedor: numeroProveedor || null,
        fecha,
        pedido_id: pedidoId || null,
      })
      onCambio()
      navigate(`/albaranes/${albaran.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <ModalPantalla title="Nuevo albarán" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          {obras.length === 0 ? (
            <EmptyState title="Hace falta una obra">Crea antes al menos una obra.</EmptyState>
          ) : (
            <div className="form-grid">
              <Field label="Tipo">
                <select
                  className="select"
                  value={tipo}
                  onChange={(e) => setTipo(e.target.value as TipoAlbaran)}
                >
                  <option value="proveedor">De un proveedor</option>
                  <option value="cliente">Para un cliente</option>
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
              <Field
                label={tipo === 'proveedor' ? 'Nº del proveedor' : 'Nº de referencia'}
                hint="El número que trae el propio albarán — opcional"
              >
                <input
                  className="input"
                  value={numeroProveedor}
                  onChange={(e) => setNumeroProveedor(e.target.value)}
                />
              </Field>
              {tipo === 'proveedor' && (
                <Field
                  label="De qué pedido viene"
                  hint={pedidos.length === 0 ? 'Sin pedidos abiertos con este proveedor en esta obra' : 'Opcional'}
                >
                  <select
                    className="select"
                    value={pedidoId}
                    onChange={(e) => setPedidoId(e.target.value)}
                    disabled={pedidos.length === 0}
                  >
                    <option value="">— Sin pedido —</option>
                    {pedidos.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.codigo}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              <Field label="Fecha">
                <input
                  className="input"
                  type="date"
                  value={fecha}
                  onChange={(e) => setFecha(e.target.value)}
                />
              </Field>
            </div>
          )}
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={obraId === '' || terceroId === ''}
            onClick={() => void guardar()}
          >
            <Plus size={16} aria-hidden="true" />
            Crear
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
