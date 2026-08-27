import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO_FACTURA_RECIBIDA, ETIQUETA_IVA, api } from '../lib/api'
import type { FacturaRecibida, ObraResumen, Tercero, TipoIVA } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoFacturasRecibidas = { onCambio: () => void }

export function useContextoFacturasRecibidas() {
  return useOutletContext<ContextoFacturasRecibidas>()
}

export function FacturasRecibidas() {
  const [items, setItems] = useState<FacturaRecibida[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.facturasRecibidas.list({ limit: LIMITE })
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

  const columnas = useMemo<ColumnaTabla<FacturaRecibida>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (f) => f.codigo, anchoInicial: 110 },
      {
        id: 'proveedor',
        encabezado: 'Proveedor',
        accessor: (f) => `${f.proveedor_razon_social} ${f.numero_proveedor}`,
        render: (f) => (
          <>
            <Link className="table__link" to={`${f.id}`}>
              {f.proveedor_razon_social}
            </Link>
            <div className="muted">Nº {f.numero_proveedor}</div>
          </>
        ),
        anchoInicial: 260,
      },
      { id: 'fecha', encabezado: 'Fecha', accessor: (f) => f.fecha, tipo: 'fecha', anchoInicial: 140 },
      {
        id: 'estado',
        encabezado: 'Estado',
        accessor: (f) => f.estado,
        render: (f) => (
          <span className={`chip chip--estado-fr-${f.estado}`}>
            {ETIQUETA_ESTADO_FACTURA_RECIBIDA[f.estado]}
          </span>
        ),
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_ESTADO_FACTURA_RECIBIDA).map(([value, label]) => ({
          value,
          label,
        })),
        anchoInicial: 130,
      },
      {
        id: 'total',
        encabezado: 'Total',
        accessor: (f) => f.total,
        render: (f) => <strong>{formatoImporte(f.total)}</strong>,
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
          <h1 className="page-title">Facturas recibidas</h1>
          <p className="page-lead">
            Lo que nos factura un proveedor, imputado a una obra. No las emitimos nosotros: sin
            serie ni numeración legal.
          </p>
        </div>
        <Tooltip texto="Registrar una factura de proveedor">
          <Link className="btn btn--primary" to="nueva">
            <Plus size={16} aria-hidden="true" />
            Nueva factura recibida
          </Link>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin facturas recibidas">Registra la primera para empezar.</EmptyState>
      ) : (
        <DataTable
          id="facturas-recibidas"
          columnas={columnas}
          datos={items}
          claveFila={(f) => f.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoFacturasRecibidas} />
    </>
  )
}

export function FacturaRecibidaCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoFacturasRecibidas()
  const [obras, setObras] = useState<ObraResumen[]>([])
  const [proveedores, setProveedores] = useState<Tercero[]>([])
  const [obraId, setObraId] = useState('')
  const [proveedorId, setProveedorId] = useState('')
  const [numero, setNumero] = useState('')
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [vencimiento, setVencimiento] = useState('')
  const [base, setBase] = useState('')
  const [tipoIva, setTipoIva] = useState<TipoIVA>('general')
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

  function cerrar() {
    navigate('/facturas-recibidas')
  }

  async function guardar() {
    setError(null)
    setGuardando(true)
    try {
      const factura = await api.facturasRecibidas.create({
        obra_id: obraId,
        proveedor_id: proveedorId,
        numero_proveedor: numero.trim(),
        fecha,
        fecha_vencimiento: vencimiento || null,
        base_imponible: base.trim(),
        tipo_iva: tipoIva,
      })
      onCambio()
      navigate(`/facturas-recibidas/${factura.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  const listo = obraId !== '' && proveedorId !== '' && numero.trim() !== '' && base.trim() !== ''

  return (
    <ModalPantalla title="Nueva factura recibida" onClose={cerrar}>
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
              <Field label="Nº de factura" hint="El número que trae la factura del proveedor">
                <input
                  className="input"
                  value={numero}
                  onChange={(e) => setNumero(e.target.value)}
                  placeholder="F/2026/118"
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
              <Field label="Vencimiento" hint="Opcional">
                <input
                  className="input"
                  type="date"
                  value={vencimiento}
                  onChange={(e) => setVencimiento(e.target.value)}
                />
              </Field>
              <Field label="Base imponible">
                <input
                  className="input"
                  inputMode="decimal"
                  value={base}
                  onChange={(e) => setBase(e.target.value)}
                />
              </Field>
              <Field label="IVA">
                <select
                  className="select"
                  value={tipoIva}
                  onChange={(e) => setTipoIva(e.target.value as TipoIVA)}
                >
                  {(Object.keys(ETIQUETA_IVA) as TipoIVA[]).map((t) => (
                    <option key={t} value={t}>
                      {ETIQUETA_IVA[t]}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          )}
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button className="btn btn--primary" disabled={!listo || guardando} onClick={() => void guardar()}>
            <Plus size={16} aria-hidden="true" />
            {guardando ? 'Creando…' : 'Crear'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
