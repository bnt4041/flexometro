import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { Plus } from 'lucide-react'

import { Checkbox, ErrorNotice, Field, ModalPantalla, EmptyState, Tooltip } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { api } from '../lib/api'
import type { Tercero } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`), de sobra para lo que cabe filtrar/ordenar a mano en
// una pantalla.
const LIMITE = 500

export type ContextoTerceros = { onCambio: () => void }

/** Contexto que las rutas hijas (`:id`, `nuevo`, montadas vía `<Outlet/>`)
 *  usan para avisar al listado de que refresque tras crear/editar/borrar —
 *  el listado sigue montado detrás del modal gigante, no se recarga la
 *  página. */
export function useContextoTerceros() {
  return useOutletContext<ContextoTerceros>()
}

export function Terceros() {
  const { t } = useTranslation()
  const [items, setItems] = useState<Tercero[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.terceros.list({ limit: LIMITE })
      setItems(page.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    } finally {
      setCargando(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const inactivoLabel = t('terceros.inactivo')

  const columnas = useMemo<ColumnaTabla<Tercero>[]>(
    () => [
      { id: 'codigo', encabezado: t('terceros.columnaCodigo'), accessor: (t) => t.codigo, anchoInicial: 110 },
      {
        id: 'razon_social',
        encabezado: t('terceros.columnaRazonSocial'),
        accessor: (t) => t.razon_social,
        render: (t) => (
          <>
            <Link className="table__link" to={`${t.id}`}>
              {t.razon_social}
            </Link>
            {!t.activo && <span className="chip chip--inactivo"> {inactivoLabel}</span>}
          </>
        ),
        anchoInicial: 260,
      },
      { id: 'nif', encabezado: t('terceros.columnaNif'), accessor: (t) => t.nif ?? '', anchoInicial: 120 },
      {
        id: 'roles',
        encabezado: t('terceros.columnaRoles'),
        accessor: (t) =>
          [t.es_cliente && 'cliente', t.es_proveedor && 'proveedor', t.es_subcontratista && 'subcontratista']
            .filter(Boolean)
            .join(', '),
        render: (t) => <RolesChips tercero={t} />,
        tipo: 'select',
        opciones: [
          { value: 'cliente', label: t('terceros.rolCliente') },
          { value: 'proveedor', label: t('terceros.rolProveedor') },
          { value: 'subcontratista', label: t('terceros.rolSubcontratista') },
        ],
      },
      { id: 'ciudad', encabezado: t('terceros.columnaPoblacion'), accessor: (t) => t.ciudad ?? '' },
      {
        id: 'dias_pago',
        encabezado: t('terceros.columnaPago'),
        accessor: (t) => t.dias_pago,
        render: (t) => (t.dias_pago !== null ? `${t.dias_pago} d` : <span className="muted">—</span>),
        anchoInicial: 90,
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t],
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{t('terceros.titulo')}</h1>
          <p className="page-lead">{t('terceros.descripcion')}</p>
        </div>
        <Tooltip texto={t('terceros.nuevo')}>
          <Link className="btn btn--primary" to="nuevo">
            <Plus size={16} aria-hidden="true" />
            {t('terceros.nuevo')}
          </Link>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title={t('terceros.sinTerceros')}>{t('terceros.creaElPrimero')}</EmptyState>
      ) : (
        <DataTable
          id="terceros"
          columnas={columnas}
          datos={items}
          claveFila={(t) => t.id}
          vacio={t('comun.sinResultadosConFiltros')}
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoTerceros} />
    </>
  )
}

export function RolesChips({ tercero }: { tercero: Tercero }) {
  const { t } = useTranslation()
  const etiqueta: Record<string, string> = {
    cliente: t('terceros.rolCliente'),
    proveedor: t('terceros.rolProveedor'),
    subcontratista: t('terceros.rolSubcontratista'),
  }
  const roles: string[] = []
  if (tercero.es_cliente) roles.push('cliente')
  if (tercero.es_proveedor) roles.push('proveedor')
  if (tercero.es_subcontratista) roles.push('subcontratista')
  if (roles.length === 0) return <span className="muted">—</span>
  return (
    <span className="chips">
      {roles.map((rol) => (
        <span key={rol} className={`chip chip--${rol}`}>
          {etiqueta[rol]}
        </span>
      ))}
    </span>
  )
}

export function TerceroCrear() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { onCambio } = useContextoTerceros()
  const [razonSocial, setRazonSocial] = useState('')
  const [nif, setNif] = useState('')
  const [esCliente, setEsCliente] = useState(false)
  const [esProveedor, setEsProveedor] = useState(false)
  const [esSubcontratista, setEsSubcontratista] = useState(false)
  const [ciudad, setCiudad] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  function cerrar() {
    navigate('/terceros')
  }

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.terceros.create({
        razon_social: razonSocial,
        nif: nif || null,
        es_cliente: esCliente,
        es_proveedor: esProveedor,
        es_subcontratista: esSubcontratista,
        ciudad: ciudad || null,
      })
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    } finally {
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title={t('terceros.nuevo')} onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <div className="form-grid">
            <Field label={t('terceros.razonSocial')}>
              <input
                className="input"
                value={razonSocial}
                onChange={(e) => setRazonSocial(e.target.value)}
                autoFocus
              />
            </Field>
            <Field label={t('terceros.nifCif')} hint={t('terceros.nifCifHint')}>
              <input className="input" value={nif} onChange={(e) => setNif(e.target.value)} />
            </Field>
            <Field label={t('terceros.poblacion')}>
              <input className="input" value={ciudad} onChange={(e) => setCiudad(e.target.value)} />
            </Field>
          </div>
          <div style={{ display: 'flex', gap: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
            <Checkbox label={t('terceros.rolCliente')} checked={esCliente} onChange={setEsCliente} />
            <Checkbox label={t('terceros.rolProveedor')} checked={esProveedor} onChange={setEsProveedor} />
            <Checkbox
              label={t('terceros.rolSubcontratista')}
              checked={esSubcontratista}
              onChange={setEsSubcontratista}
            />
          </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            {t('comun.cancelar')}
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || razonSocial.trim() === ''}
            onClick={() => void guardar()}
          >
            {guardando ? t('comun.creando') : t('comun.crear')}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
