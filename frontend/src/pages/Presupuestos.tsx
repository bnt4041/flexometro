import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO, api } from '../lib/api'
import type { PresupuestoResumen, Tercero } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`). `soloUltima` sigue siendo un filtro de servidor (cambia
// qué versiones se traen), no un filtro de columna.
const LIMITE = 500

export type ContextoPresupuestos = { onCambio: () => void }

export function useContextoPresupuestos() {
  return useOutletContext<ContextoPresupuestos>()
}

export function Presupuestos() {
  const [items, setItems] = useState<PresupuestoResumen[]>([])
  const [pestana, setPestana] = useState<'obras' | 'plantillas'>('obras')
  const [soloUltima, setSoloUltima] = useState(true)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [instanciando, setInstanciando] = useState<PresupuestoResumen | null>(null)

  const esPlantillas = pestana === 'plantillas'

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.presupuestos.list({
        es_plantilla: esPlantillas,
        solo_ultima_version: !esPlantillas && soloUltima,
        limit: LIMITE,
      })
      setItems(page.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [esPlantillas, soloUltima])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const columnasObras = useMemo<ColumnaTabla<PresupuestoResumen>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (p) => p.codigo, anchoInicial: 110 },
      {
        id: 'obra',
        encabezado: 'Obra',
        accessor: (p) => `${p.nombre} ${p.emplazamiento ?? ''}`,
        render: (p) => (
          <>
            <Link className="table__link" to={`${p.id}`}>
              {p.nombre}
            </Link>
            {p.version > 1 && <span className="badge"> v{p.version}</span>}
            {p.emplazamiento && <div className="muted">{p.emplazamiento}</div>}
          </>
        ),
        anchoInicial: 280,
      },
      { id: 'fecha', encabezado: 'Fecha', accessor: (p) => p.fecha, tipo: 'fecha', anchoInicial: 160 },
      {
        id: 'estado',
        encabezado: 'Estado',
        accessor: (p) => p.estado,
        render: (p) => <span className={`chip chip--estado-${p.estado}`}>{ETIQUETA_ESTADO[p.estado]}</span>,
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_ESTADO).map(([value, label]) => ({ value, label })),
        anchoInicial: 140,
      },
      { id: 'pem', encabezado: 'PEM', accessor: (p) => p.pem, tipo: 'importe', anchoInicial: 110 },
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

  const columnasPlantillas = useMemo<ColumnaTabla<PresupuestoResumen>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (p) => p.codigo, anchoInicial: 110 },
      {
        id: 'obra',
        encabezado: 'Obra',
        accessor: (p) => p.nombre,
        render: (p) => (
          <Link className="table__link" to={`${p.id}`}>
            {p.nombre}
          </Link>
        ),
        anchoInicial: 280,
      },
      { id: 'tipo_obra', encabezado: 'Tipo de obra', accessor: (p) => p.tipo_obra, anchoInicial: 160 },
      {
        id: 'usar',
        encabezado: '',
        accessor: () => '',
        render: (p) => (
          <button className="btn btn--sm" onClick={() => setInstanciando(p)}>
            Usar plantilla
          </button>
        ),
        ordenable: false,
        filtrable: false,
        anchoInicial: 140,
      },
      { id: 'pem', encabezado: 'PEM', accessor: (p) => p.pem, tipo: 'importe', anchoInicial: 110 },
    ],
    [],
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{esPlantillas ? 'Plantillas' : 'Presupuestos'}</h1>
          <p className="page-lead">
            {esPlantillas
              ? 'Estructuras reutilizables por tipo de obra. Instanciar una crea un presupuesto nuevo con sus capítulos y partidas.'
              : 'Capítulos, partidas y mediciones. En borrador siguen al banco de precios; al emitirlos, los precios se congelan.'}
          </p>
        </div>
        {!esPlantillas && (
          <Tooltip texto="Crear un presupuesto nuevo">
            <Link className="btn btn--primary" to="nuevo">
              <Plus size={16} aria-hidden="true" />
              Nuevo presupuesto
            </Link>
          </Tooltip>
        )}
      </div>

      <div className="pestanas">
        <button
          className={pestana === 'obras' ? 'pestanas__item is-activa' : 'pestanas__item'}
          onClick={() => setPestana('obras')}
        >
          Presupuestos
        </button>
        <button
          className={pestana === 'plantillas' ? 'pestanas__item is-activa' : 'pestanas__item'}
          onClick={() => setPestana('plantillas')}
        >
          Plantillas
        </button>
      </div>

      {!esPlantillas && (
        <div className="toolbar">
          <label className="checkbox">
            <input
              type="checkbox"
              checked={soloUltima}
              onChange={(e) => setSoloUltima(e.target.checked)}
            />
            <span>Solo la última versión</span>
          </label>
        </div>
      )}

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin presupuestos">Crea el primero para empezar.</EmptyState>
      ) : (
        <DataTable
          id={esPlantillas ? 'presupuestos-plantillas' : 'presupuestos-obras'}
          columnas={esPlantillas ? columnasPlantillas : columnasObras}
          datos={items}
          claveFila={(p) => p.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoPresupuestos} />

      {instanciando && (
        <InstanciarModal
          plantilla={instanciando}
          onClose={() => setInstanciando(null)}
          onCreado={() => {
            setInstanciando(null)
            setPestana('obras')
          }}
        />
      )}
    </>
  )
}

function InstanciarModal({
  plantilla,
  onClose,
  onCreado,
}: {
  plantilla: PresupuestoResumen
  onClose: () => void
  onCreado: () => void
}) {
  const navegar = useNavigate()
  const [nombre, setNombre] = useState('')
  const [emplazamiento, setEmplazamiento] = useState('')
  const [clienteId, setClienteId] = useState('')
  const [clientes, setClientes] = useState<Tercero[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api.terceros
      .list({ rol: 'cliente', activo: true, limit: 500 })
      .then((page) => setClientes(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  async function guardar() {
    try {
      const nuevo = await api.presupuestos.instanciar(plantilla.id, {
        nombre,
        cliente_id: clienteId || null,
        emplazamiento: emplazamiento || null,
      })
      onCreado()
      navegar(`/presupuestos/${nuevo.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title={`Nuevo presupuesto desde «${plantilla.nombre}»`} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          Se copian los capítulos y las partidas de la plantilla. Las mediciones se rellenan
          después, obra a obra.
        </p>
        <div className="form-grid">
          <Field label="Obra">
            <input
              className="input"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Emplazamiento">
            <input
              className="input"
              value={emplazamiento}
              onChange={(e) => setEmplazamiento(e.target.value)}
            />
          </Field>
          <Field label="Cliente">
            <select
              className="select"
              value={clienteId}
              onChange={(e) => setClienteId(e.target.value)}
            >
              <option value="">Sin asignar</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.razon_social}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={nombre.trim() === ''}
          onClick={() => void guardar()}
        >
          Crear presupuesto
        </button>
      </div>
    </Modal>
  )
}

export function PresupuestoCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoPresupuestos()
  const [nombre, setNombre] = useState('')
  const [emplazamiento, setEmplazamiento] = useState('')
  const [clienteId, setClienteId] = useState('')
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [gg, setGg] = useState('13.00')
  const [bi, setBi] = useState('6.00')
  const [clientes, setClientes] = useState<Tercero[]>([])
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  function cerrar() {
    navigate('/presupuestos')
  }

  useEffect(() => {
    void api.terceros
      .list({ rol: 'cliente', activo: true, limit: 500 })
      .then((page) => setClientes(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.presupuestos.create({
        nombre,
        emplazamiento: emplazamiento || null,
        cliente_id: clienteId || null,
        fecha,
        gastos_generales: gg,
        beneficio_industrial: bi,
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
    <ModalPantalla title="Nuevo presupuesto" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <div className="form-grid">
            <Field label="Obra">
              <input
                className="input"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                autoFocus
              />
            </Field>
            <Field label="Emplazamiento">
              <input
                className="input"
                value={emplazamiento}
                onChange={(e) => setEmplazamiento(e.target.value)}
              />
            </Field>
            <Field label="Cliente">
              <select
                className="select"
                value={clienteId}
                onChange={(e) => setClienteId(e.target.value)}
              >
                <option value="">Sin asignar</option>
                {clientes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.razon_social}
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
            <Field label="Gastos generales (%)" hint="13 % por defecto (RD 1098/2001)">
              <input
                className="input"
                type="number"
                step="0.01"
                value={gg}
                onChange={(e) => setGg(e.target.value)}
              />
            </Field>
            <Field label="Beneficio industrial (%)" hint="6 % por defecto">
              <input
                className="input"
                type="number"
                step="0.01"
                value={bi}
                onChange={(e) => setBi(e.target.value)}
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
            disabled={guardando || nombre.trim() === ''}
            onClick={() => void guardar()}
          >
            {guardando ? 'Guardando…' : 'Crear'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
