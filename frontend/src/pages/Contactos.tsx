import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState, ErrorNotice } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { api } from '../lib/api'
import type { Contacto } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

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

  const columnas = useMemo<ColumnaTabla<Contacto>[]>(
    () => [
      {
        id: 'nombre',
        encabezado: 'Nombre',
        accessor: (c) => `${c.nombre} ${c.apellidos ?? ''}`,
        render: (c) => (
          <>
            {c.nombre} {c.apellidos ?? ''}
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
        accessor: () => '',
        render: (c) =>
          c.tercero_id ? (
            <Link className="table__link" to={`/terceros/${c.tercero_id}`}>
              Ver ficha
            </Link>
          ) : (
            <span className="muted">Sin empresa</span>
          ),
        ordenable: false,
        filtrable: false,
        anchoInicial: 120,
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
    </>
  )
}
