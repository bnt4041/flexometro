import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'

import { EmptyState, ErrorNotice, Field, ModalPantalla, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO_ALBARAN, api } from '../lib/api'
import type { AlbaranResumen, ObraResumen, Tercero } from '../lib/api'

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
        id: 'proveedor',
        encabezado: 'Proveedor',
        accessor: (a) => `${a.proveedor_razon_social} ${a.numero_proveedor ?? ''}`,
        render: (a) => (
          <>
            <Link className="table__link" to={`${a.id}`}>
              {a.proveedor_razon_social}
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
          <p className="page-lead">Material recibido en obra desde un proveedor.</p>
        </div>
        <Link className="btn btn--primary" to="nuevo">
          Nuevo albarán
        </Link>
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
  const [proveedores, setProveedores] = useState<Tercero[]>([])
  const [obraId, setObraId] = useState('')
  const [proveedorId, setProveedorId] = useState('')
  const [numeroProveedor, setNumeroProveedor] = useState('')
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [error, setError] = useState<string | null>(null)

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

  function cerrar() {
    navigate('/albaranes')
  }

  async function guardar() {
    setError(null)
    try {
      const albaran = await api.albaranes.create({
        obra_id: obraId,
        proveedor_id: proveedorId,
        numero_proveedor: numeroProveedor || null,
        fecha,
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
          {obras.length === 0 || proveedores.length === 0 ? (
            <EmptyState title="Hace falta una obra y un proveedor">
              Crea antes al menos una obra y marca algún tercero con el rol de proveedor.
            </EmptyState>
          ) : (
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
              <Field label="Nº del proveedor" hint="El número que trae el propio albarán">
                <input
                  className="input"
                  value={numeroProveedor}
                  onChange={(e) => setNumeroProveedor(e.target.value)}
                />
              </Field>
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
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={obraId === '' || proveedorId === ''}
            onClick={() => void guardar()}
          >
            Crear
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
