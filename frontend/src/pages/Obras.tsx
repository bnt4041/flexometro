import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla, Tooltip } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO_OBRA, api } from '../lib/api'
import type { ObraResumen, PresupuestoResumen } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoObras = { onCambio: () => void }

export function useContextoObras() {
  return useOutletContext<ContextoObras>()
}

export function Obras() {
  const [items, setItems] = useState<ObraResumen[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.obras.list({ limit: LIMITE })
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

  const columnas = useMemo<ColumnaTabla<ObraResumen>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (o) => o.codigo, anchoInicial: 110 },
      {
        id: 'obra',
        encabezado: 'Obra',
        accessor: (o) => `${o.nombre} ${o.presupuesto_codigo} ${o.presupuesto_nombre}`,
        render: (o) => (
          <>
            <Link className="table__link" to={`${o.id}`}>
              {o.nombre}
            </Link>
            <div className="muted">
              {o.presupuesto_codigo} · {o.presupuesto_nombre}
            </div>
          </>
        ),
        anchoInicial: 300,
      },
      {
        id: 'estado',
        encabezado: 'Estado',
        accessor: (o) => o.estado,
        render: (o) => <span className={`chip chip--estado-${o.estado}`}>{ETIQUETA_ESTADO_OBRA[o.estado]}</span>,
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_ESTADO_OBRA).map(([value, label]) => ({ value, label })),
        anchoInicial: 150,
      },
      { id: 'pem', encabezado: 'PEM', accessor: (o) => o.pem, tipo: 'importe', anchoInicial: 110 },
    ],
    [],
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Obras</h1>
          <p className="page-lead">
            Ejecución de un presupuesto: personal asignado, partes de trabajo y coste real frente
            a lo presupuestado.
          </p>
        </div>
        <Tooltip texto="Ejecutar un presupuesto aprobado como obra">
          <Link className="btn btn--primary" to="nueva">
            <Plus size={16} aria-hidden="true" />
            Nueva obra
          </Link>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin obras">
          Crea una obra a partir de un presupuesto aprobado para empezar a registrar coste real.
        </EmptyState>
      ) : (
        <DataTable
          id="obras"
          columnas={columnas}
          datos={items}
          claveFila={(o) => o.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoObras} />
    </>
  )
}

export function ObraCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoObras()
  const [nombre, setNombre] = useState('')
  const [presupuestoId, setPresupuestoId] = useState('')
  const [fechaInicio, setFechaInicio] = useState(new Date().toISOString().slice(0, 10))
  const [presupuestos, setPresupuestos] = useState<PresupuestoResumen[]>([])
  const [error, setError] = useState<string | null>(null)

  function cerrar() {
    navigate('/obras')
  }

  useEffect(() => {
    void api.presupuestos
      .list({ solo_ultima_version: true, limit: 100 })
      .then((page) => setPresupuestos(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  async function guardar() {
    setError(null)
    try {
      const obra = await api.obras.create({
        nombre,
        presupuesto_id: presupuestoId,
        fecha_inicio: fechaInicio || null,
      })
      onCambio()
      navigate(`/obras/${obra.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <ModalPantalla title="Nueva obra" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <p className="form-section__note">
            Cada presupuesto solo puede ejecutarse en una obra. Si no aparece el que buscas, puede
            que ya tenga una obra asociada.
          </p>
          <div className="form-grid">
            <Field ancho="doble" label="Nombre de la obra">
              <input
                className="input"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                autoFocus
              />
            </Field>
            <Field ancho="doble" label="Presupuesto a ejecutar">
              <select
                className="select"
                value={presupuestoId}
                onChange={(e) => setPresupuestoId(e.target.value)}
              >
                <option value="">Elige un presupuesto…</option>
                {presupuestos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.codigo} · {p.nombre}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Fecha de inicio">
              <input
                className="input"
                type="date"
                value={fechaInicio}
                onChange={(e) => setFechaInicio(e.target.value)}
              />
            </Field>
          </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={nombre.trim() === '' || presupuestoId === ''}
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
