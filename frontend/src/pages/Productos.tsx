import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'

import { EmptyState, ErrorNotice, Field, ModalPantalla } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_IVA, ETIQUETA_TIPO_PRODUCTO, api } from '../lib/api'
import type { Producto, TipoIVA, TipoProducto } from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoProductos = { onCambio: () => void }

export function useContextoProductos() {
  return useOutletContext<ContextoProductos>()
}

export function Productos() {
  const [items, setItems] = useState<Producto[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.productos.list({ limit: LIMITE })
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

  const columnas = useMemo<ColumnaTabla<Producto>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (p) => p.codigo, anchoInicial: 110 },
      {
        id: 'resumen',
        encabezado: 'Descripción',
        accessor: (p) => p.resumen,
        render: (p) => (
          <>
            <Link className="table__link" to={`${p.id}`}>
              {p.resumen}
            </Link>
            {!p.activo && <span className="chip chip--inactivo"> inactivo</span>}
          </>
        ),
        anchoInicial: 280,
      },
      {
        id: 'tipo',
        encabezado: 'Tipo',
        accessor: (p) => p.tipo,
        render: (p) => ETIQUETA_TIPO_PRODUCTO[p.tipo],
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_TIPO_PRODUCTO).map(([value, label]) => ({ value, label })),
        anchoInicial: 130,
      },
      { id: 'unidad', encabezado: 'Ud.', accessor: (p) => p.unidad, anchoInicial: 70 },
      { id: 'precio_venta', encabezado: 'P. venta', accessor: (p) => p.precio_venta, tipo: 'importe', anchoInicial: 110 },
      {
        id: 'origen_dato',
        encabezado: 'Origen',
        accessor: (p) => p.origen_dato,
        render: (p) => <span className="badge">{p.origen_dato}</span>,
        anchoInicial: 110,
      },
    ],
    [],
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Productos y servicios</h1>
          <p className="page-lead">
            Catálogo propio de la empresa. Cada producto puede tener tarifas de varios
            proveedores; la preferente es la que alimentará el precio básico.
          </p>
        </div>
        <Link className="btn btn--primary" to="nuevo">
          Nuevo producto
        </Link>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin resultados">Crea el primer producto del catálogo.</EmptyState>
      ) : (
        <DataTable
          id="productos"
          columnas={columnas}
          datos={items}
          claveFila={(p) => p.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoProductos} />
    </>
  )
}

export function ProductoCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoProductos()
  const unidadesMedida = useDiccionario('unidad_medida')
  const [resumen, setResumen] = useState('')
  const [tipo, setTipo] = useState<TipoProducto>('material')
  const [unidad, setUnidad] = useState('ud')
  const [tipoIva, setTipoIva] = useState<TipoIVA>('general')
  const [precioVenta, setPrecioVenta] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  function cerrar() {
    navigate('/productos')
  }

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.productos.create({
        resumen,
        tipo,
        unidad,
        tipo_iva: tipoIva,
        precio_venta: precioVenta || null,
      })
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Nuevo producto" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <div className="form-grid">
            <Field label="Descripción corta" hint="El texto que se imprime en presupuestos">
              <input
                className="input"
                value={resumen}
                onChange={(e) => setResumen(e.target.value)}
                autoFocus
              />
            </Field>
            <Field label="Tipo">
              <select
                className="select"
                value={tipo}
                onChange={(e) => setTipo(e.target.value as TipoProducto)}
              >
                {Object.entries(ETIQUETA_TIPO_PRODUCTO).map(([clave, etiqueta]) => (
                  <option key={clave} value={clave}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Unidad">
              <select className="select" value={unidad} onChange={(e) => setUnidad(e.target.value)}>
                {unidadesMedida.map((u) => (
                  <option key={u.clave} value={u.clave}>
                    {u.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tipo de IVA">
              <select
                className="select"
                value={tipoIva}
                onChange={(e) => setTipoIva(e.target.value as TipoIVA)}
              >
                {Object.entries(ETIQUETA_IVA).map(([clave, etiqueta]) => (
                  <option key={clave} value={clave}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Precio de venta">
              <input
                className="input"
                type="number"
                step="0.01"
                value={precioVenta}
                onChange={(e) => setPrecioVenta(e.target.value)}
              />
            </Field>
          </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || resumen.trim() === ''}
            onClick={() => void guardar()}
          >
            {guardando ? 'Guardando…' : 'Crear'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
