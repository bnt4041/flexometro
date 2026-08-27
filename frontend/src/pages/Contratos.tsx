import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO_CONTRATO, ETIQUETA_TIPO_CONTRATO, api } from '../lib/api'
import type { ContratoResumen, ObraResumen, PresupuestoResumen, Tercero, TipoContrato } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoContratos = { onCambio: () => void }

export function useContextoContratos() {
  return useOutletContext<ContextoContratos>()
}

export function Contratos() {
  const [items, setItems] = useState<ContratoResumen[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.contratos.list({ limit: LIMITE })
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

  const columnas = useMemo<ColumnaTabla<ContratoResumen>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (c) => c.codigo, anchoInicial: 110 },
      {
        id: 'tipo',
        encabezado: 'Tipo',
        accessor: (c) => c.tipo,
        render: (c) => ETIQUETA_TIPO_CONTRATO[c.tipo],
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_TIPO_CONTRATO).map(([value, label]) => ({ value, label })),
        anchoInicial: 110,
      },
      {
        id: 'tercero',
        encabezado: 'Cliente / proveedor',
        accessor: (c) => c.tercero_razon_social,
        render: (c) => (
          <Link className="table__link" to={`${c.id}`}>
            {c.tercero_razon_social}
          </Link>
        ),
        anchoInicial: 240,
      },
      {
        id: 'fecha_firma',
        encabezado: 'Firma',
        accessor: (c) => c.fecha_firma ?? '',
        tipo: 'fecha',
        anchoInicial: 130,
      },
      {
        id: 'estado',
        encabezado: 'Estado',
        accessor: (c) => c.estado,
        render: (c) => (
          <span className={`chip chip--estado-contrato-${c.estado}`}>
            {ETIQUETA_ESTADO_CONTRATO[c.estado]}
          </span>
        ),
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_ESTADO_CONTRATO).map(([value, label]) => ({ value, label })),
        anchoInicial: 130,
      },
      {
        id: 'importe',
        encabezado: 'Importe',
        accessor: (c) => c.importe ?? '',
        render: (c) => (c.importe ? <strong>{formatoImporte(c.importe)}</strong> : <span className="muted">—</span>),
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
          <h1 className="page-title">Contratos</h1>
          <p className="page-lead">
            Formaliza el acuerdo de una obra — con el cliente, sobre el presupuesto aprobado, o con
            un proveedor.
          </p>
        </div>
        <Tooltip texto="Formalizar un contrato">
          <Link className="btn btn--primary" to="nuevo">
            <Plus size={16} aria-hidden="true" />
            Nuevo contrato
          </Link>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin contratos">Formaliza el primero para empezar.</EmptyState>
      ) : (
        <DataTable
          id="contratos"
          columnas={columnas}
          datos={items}
          claveFila={(c) => c.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoContratos} />
    </>
  )
}

export function ContratoCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoContratos()
  const [obras, setObras] = useState<ObraResumen[]>([])
  const [tipo, setTipo] = useState<TipoContrato>('cliente')
  const [terceros, setTerceros] = useState<Tercero[]>([])
  const [obraId, setObraId] = useState('')
  const [terceroId, setTerceroId] = useState('')
  const [fechaFirma, setFechaFirma] = useState(new Date().toISOString().slice(0, 10))
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

  // Presupuestos del tipo correspondiente, para poder enlazar el que
  // formaliza — opcional, no todo contrato tiene uno detrás todavía.
  useEffect(() => {
    setPresupuestoId('')
    void api.presupuestos
      .list({ tipo, limit: 200 })
      .then((page) => setPresupuestos(page.items))
      .catch(() => setPresupuestos([]))
  }, [tipo])

  function cerrar() {
    navigate('/contratos')
  }

  async function guardar() {
    setError(null)
    setGuardando(true)
    try {
      const contrato = await api.contratos.create({
        tipo,
        obra_id: obraId,
        cliente_id: tipo === 'cliente' ? terceroId : null,
        proveedor_id: tipo === 'proveedor' ? terceroId : null,
        presupuesto_id: presupuestoId || null,
        fecha_firma: fechaFirma || null,
      })
      onCambio()
      navigate(`/contratos/${contrato.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Nuevo contrato" onClose={cerrar}>
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
                  onChange={(e) => setTipo(e.target.value as TipoContrato)}
                >
                  <option value="cliente">Con el cliente</option>
                  <option value="proveedor">Con un proveedor</option>
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
              <Field label={tipo === 'cliente' ? 'Cliente' : 'Proveedor'}>
                {terceros.length === 0 ? (
                  <p className="muted">
                    No hay ningún tercero con el rol de {tipo === 'cliente' ? 'cliente' : 'proveedor'}
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
              <Field label="Fecha de firma" hint="Opcional">
                <input
                  className="input"
                  type="date"
                  value={fechaFirma}
                  onChange={(e) => setFechaFirma(e.target.value)}
                />
              </Field>
              <Field
                ancho="doble"
                label="Presupuesto que formaliza"
                hint={
                  presupuestos.length === 0
                    ? `Sin presupuestos de ${tipo === 'cliente' ? 'cliente' : 'proveedor'} disponibles`
                    : 'Opcional'
                }
              >
                <select
                  className="select"
                  value={presupuestoId}
                  onChange={(e) => setPresupuestoId(e.target.value)}
                  disabled={presupuestos.length === 0}
                >
                  <option value="">— Sin presupuesto enlazado —</option>
                  {presupuestos.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.codigo} · {p.nombre}
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
