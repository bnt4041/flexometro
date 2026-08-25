import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet } from 'react-router-dom'

import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import { EmptyState, ErrorNotice, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { PresupuestoResumen, Tercero } from '../lib/api'
import type { ContextoPresupuestos } from './Presupuestos'

const LIMITE = 500

/** Las ofertas que un proveedor ha devuelto al responder una solicitud de
 *  precios (ver plan «Solicitud de precios a proveedor», §4/§6): mismo
 *  `Presupuesto` que el de cliente, filtrado por `tipo === 'proveedor'`, y
 *  abierto en la misma ficha (`/presupuestos/:id`) — no hay una ficha propia
 *  que mantener aparte, todo el árbol de capítulos/partidas/mediciones ya
 *  vale tal cual. */
export function PresupuestosProveedor() {
  const [items, setItems] = useState<PresupuestoResumen[]>([])
  const [proveedores, setProveedores] = useState<Map<string, string>>(new Map())
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const [pagina, terceros] = await Promise.all([
        api.presupuestos.list({ tipo: 'proveedor', limit: LIMITE }),
        api.terceros.list({ rol: 'proveedor', limit: LIMITE }),
      ])
      setItems(pagina.items)
      setProveedores(new Map(terceros.items.map((t: Tercero) => [t.id, t.razon_social])))
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

  const columnas = useMemo<ColumnaTabla<PresupuestoResumen>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (p) => p.codigo, anchoInicial: 110 },
      {
        id: 'nombre',
        encabezado: 'Oferta',
        accessor: (p) => p.nombre,
        render: (p) => (
          <Link className="table__link" to={`/presupuestos/${p.id}`}>
            {p.nombre}
          </Link>
        ),
        anchoInicial: 320,
      },
      {
        id: 'proveedor',
        encabezado: 'Proveedor',
        accessor: (p) => (p.proveedor_id ? proveedores.get(p.proveedor_id) ?? '' : ''),
        anchoInicial: 220,
      },
      { id: 'fecha', encabezado: 'Fecha', accessor: (p) => p.created_at, tipo: 'fecha', anchoInicial: 160 },
      {
        id: 'total',
        encabezado: 'Total',
        accessor: (p) => p.total,
        render: (p) => <strong>{formatoImporte(p.total)}</strong>,
        tipo: 'importe',
        anchoInicial: 110,
      },
    ],
    [proveedores],
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Presupuestos de proveedor</h1>
          <p className="page-lead">
            Ofertas recibidas al pedir precio a un proveedor desde un presupuesto de cliente.
          </p>
        </div>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Todavía no hay ninguna oferta">
          Se generan solas al pedir precios a un proveedor desde un presupuesto (menú contextual
          «Solicitar precios…») y que el proveedor responda.
        </EmptyState>
      ) : (
        <DataTable
          id="presupuestos-proveedor"
          columnas={columnas}
          datos={items}
          claveFila={(p) => p.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoPresupuestos} />
    </>
  )
}
