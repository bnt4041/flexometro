import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useOutletContext } from 'react-router-dom'

import { EmptyState, ErrorNotice } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { ETIQUETA_ESTADO_CERTIFICACION, api } from '../lib/api'
import type { Certificacion, ObraResumen } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoCertificaciones = { onCambio: () => void }

export function useContextoCertificaciones() {
  return useOutletContext<ContextoCertificaciones>()
}

export function Certificaciones() {
  const [items, setItems] = useState<Certificacion[]>([])
  const [obras, setObras] = useState<Record<string, ObraResumen>>({})
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.certificaciones.list({ limit: LIMITE })
      setItems(page.items)

      const obrasPage = await api.obras.list({ limit: 500 })
      setObras(Object.fromEntries(obrasPage.items.map((o) => [o.id, o])))
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

  const columnas = useMemo<ColumnaTabla<Certificacion>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (c) => c.codigo, anchoInicial: 110 },
      {
        id: 'obra',
        encabezado: 'Obra',
        accessor: (c) => `${c.numero} ${obras[c.obra_id]?.nombre ?? obras[c.obra_id]?.codigo ?? c.obra_id}`,
        render: (c) => (
          <Link className="table__link" to={`${c.id}`}>
            Nº {c.numero} — {obras[c.obra_id]?.nombre ?? obras[c.obra_id]?.codigo ?? c.obra_id}
          </Link>
        ),
        anchoInicial: 320,
      },
      { id: 'fecha', encabezado: 'Fecha', accessor: (c) => c.fecha, tipo: 'fecha', anchoInicial: 160 },
      {
        id: 'estado',
        encabezado: 'Estado',
        accessor: (c) => c.estado,
        render: (c) => (
          <span className={`chip chip--estado-cert-${c.estado}`}>{ETIQUETA_ESTADO_CERTIFICACION[c.estado]}</span>
        ),
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_ESTADO_CERTIFICACION).map(([value, label]) => ({ value, label })),
        anchoInicial: 140,
      },
    ],
    [obras],
  )

  return (
    <>
      <h1 className="page-title">Certificaciones</h1>
      <p className="page-lead">
        Medición acumulada de obra ejecutada. Se crean desde la ficha de cada obra.
      </p>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin certificaciones">Entra en una obra para crear la primera.</EmptyState>
      ) : (
        <DataTable
          id="certificaciones"
          columnas={columnas}
          datos={items}
          claveFila={(c) => c.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoCertificaciones} />
    </>
  )
}
