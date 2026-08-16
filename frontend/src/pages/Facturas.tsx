import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import {
  ETIQUETA_ESTADO_FACTURA,
  ETIQUETA_IVA,
  ETIQUETA_SITUACION_COBRO,
  api,
} from '../lib/api'
import type { FacturaResumen, ObraResumen, TipoIVA } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoFacturas = { onCambio: () => void }

export function useContextoFacturas() {
  return useOutletContext<ContextoFacturas>()
}

function numeroFactura(f: FacturaResumen): string {
  return f.numero ? `${f.serie}/${String(f.numero).padStart(5, '0')}` : f.codigo
}

export function Facturas() {
  const [items, setItems] = useState<FacturaResumen[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.facturas.list({ limit: LIMITE })
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

  const columnas = useMemo<ColumnaTabla<FacturaResumen>[]>(
    () => [
      { id: 'numero', encabezado: 'Número', accessor: (f) => numeroFactura(f), anchoInicial: 130 },
      {
        id: 'cliente',
        encabezado: 'Cliente',
        accessor: (f) => `${f.cliente_razon_social} ${f.concepto}`,
        render: (f) => (
          <>
            <Link className="table__link" to={`${f.id}`}>
              {f.cliente_razon_social}
            </Link>
            <div className="muted">{f.concepto}</div>
          </>
        ),
        anchoInicial: 260,
      },
      {
        id: 'estado',
        encabezado: 'Estado',
        accessor: (f) => f.estado,
        render: (f) => <span className={`chip chip--estado-${f.estado}`}>{ETIQUETA_ESTADO_FACTURA[f.estado]}</span>,
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_ESTADO_FACTURA).map(([value, label]) => ({ value, label })),
        anchoInicial: 130,
      },
      {
        id: 'cobro',
        encabezado: 'Cobro',
        accessor: (f) => (f.estado === 'emitida' ? f.situacion_cobro : ''),
        render: (f) =>
          f.estado === 'emitida' && (
            <span className={`chip chip--cobro-${f.situacion_cobro}`}>
              {ETIQUETA_SITUACION_COBRO[f.situacion_cobro]}
              {f.vencida && ' · vencida'}
            </span>
          ),
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_SITUACION_COBRO).map(([value, label]) => ({ value, label })),
        anchoInicial: 140,
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
          <h1 className="page-title">Facturas</h1>
          <p className="page-lead">
            Documentos fiscales generados desde certificaciones o sueltos. Una vez emitida, una
            factura no se borra: se anula.
          </p>
        </div>
        <Tooltip texto="Crear una factura sin certificación previa">
          <Link className="btn btn--primary" to="nueva">
            <Plus size={16} aria-hidden="true" />
            Factura suelta
          </Link>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin facturas">
          Genera una desde una certificación emitida, o crea una suelta.
        </EmptyState>
      ) : (
        <DataTable
          id="facturas"
          columnas={columnas}
          datos={items}
          claveFila={(f) => f.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoFacturas} />
    </>
  )
}

export function FacturaSueltaCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoFacturas()
  const [obras, setObras] = useState<ObraResumen[]>([])
  const [obraId, setObraId] = useState('')
  const [concepto, setConcepto] = useState('')
  const [base, setBase] = useState('')
  const [tipoIva, setTipoIva] = useState<TipoIVA>('general')
  const [isp, setIsp] = useState(false)
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

  function cerrar() {
    navigate('/facturas')
  }

  async function guardar() {
    setError(null)
    try {
      const factura = await api.facturas.createSuelta({
        obra_id: obraId,
        concepto,
        base_imponible: base,
        tipo_iva: tipoIva,
        inversion_sujeto_pasivo: isp,
      })
      onCambio()
      navigate(`/facturas/${factura.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <ModalPantalla title="Factura suelta" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <p className="form-section__note">
            Para un anticipo, una revisión de precios o cualquier cargo que no venga de una
            certificación. El cliente se toma del presupuesto de la obra.
          </p>
          {obras.length === 0 ? (
            <EmptyState title="No hay obras">Crea primero una obra.</EmptyState>
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
              <Field label="Concepto">
                <input
                  className="input"
                  value={concepto}
                  onChange={(e) => setConcepto(e.target.value)}
                />
              </Field>
              <Field label="Base imponible">
                <input
                  className="input"
                  type="number"
                  step="0.01"
                  value={base}
                  onChange={(e) => setBase(e.target.value)}
                />
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
            </div>
          )}
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <label className="checkbox">
              <input type="checkbox" checked={isp} onChange={(e) => setIsp(e.target.checked)} />
              <span>Inversión del sujeto pasivo</span>
            </label>
          </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={obras.length === 0 || concepto.trim() === '' || base === ''}
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
