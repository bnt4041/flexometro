import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useOutletContext } from 'react-router-dom'
import { Pencil, Trash2 } from 'lucide-react'

import { EmptyState, ErrorNotice, Tooltip } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { api } from '../lib/api'
import type { Contacto } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoContactos = { onCambio: () => void }

/** Contexto que la ruta hija (`:id`, montada vía `<Outlet/>`) usa para
 *  avisar al listado de que refresque tras editar/borrar — mismo patrón que
 *  `useContextoTerceros` en `Terceros.tsx`. */
export function useContextoContactos() {
  return useOutletContext<ContextoContactos>()
}

export function Contactos() {
  const [items, setItems] = useState<Contacto[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.contactos.list({ limit: LIMITE })
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

  async function eliminar(contacto: Contacto) {
    if (!window.confirm(`¿Eliminar el contacto «${contacto.nombre}»? No se puede deshacer.`)) return
    try {
      await api.contactos.remove(contacto.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const columnas = useMemo<ColumnaTabla<Contacto>[]>(
    () => [
      {
        id: 'nombre',
        encabezado: 'Nombre',
        accessor: (c) => `${c.nombre} ${c.apellidos ?? ''}`,
        render: (c) => (
          <>
            <Link className="table__link" to={c.id}>
              {c.nombre} {c.apellidos ?? ''}
            </Link>
            {c.es_principal && <span className="chip chip--cliente"> principal</span>}
          </>
        ),
        anchoInicial: 220,
      },
      { id: 'cargo', encabezado: 'Cargo', accessor: (c) => c.cargo, anchoInicial: 160 },
      { id: 'email', encabezado: 'Email', accessor: (c) => c.email, anchoInicial: 200 },
      { id: 'telefono', encabezado: 'Teléfono', accessor: (c) => c.telefono ?? c.movil, anchoInicial: 130 },
      {
        id: 'empresa',
        encabezado: 'Empresa',
        accessor: (c) => c.tercero_razon_social ?? '',
        render: (c) =>
          c.tercero_id ? (
            <Link className="table__link" to={`/terceros/${c.tercero_id}`}>
              {c.tercero_razon_social}
            </Link>
          ) : (
            <span className="muted">Sin empresa</span>
          ),
        anchoInicial: 180,
      },
      {
        id: 'acciones',
        encabezado: '',
        accessor: () => '',
        render: (c) => (
          <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
            <Tooltip texto="Editar">
              <Link className="btn btn--sm" to={c.id}>
                <Pencil size={14} aria-hidden="true" />
                Editar
              </Link>
            </Tooltip>
            <Tooltip texto="Eliminar">
              <button className="btn btn--sm btn--danger" onClick={() => void eliminar(c)}>
                <Trash2 size={14} aria-hidden="true" />
                Eliminar
              </button>
            </Tooltip>
          </div>
        ),
        ordenable: false,
        filtrable: false,
        anchoInicial: 160,
      },
    ],
    [],
  )

  return (
    <>
      <h1 className="page-title">Contactos</h1>
      <p className="page-lead">
        Todas las personas, colguen o no de un tercero. Los contactos sueltos (una dirección
        facultativa, un jefe de obra de la propiedad) no necesitan empresa.
      </p>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin contactos">Se crean desde la ficha de un tercero.</EmptyState>
      ) : (
        <DataTable
          id="contactos"
          columnas={columnas}
          datos={items}
          claveFila={(c) => c.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoContactos} />
    </>
  )
}
