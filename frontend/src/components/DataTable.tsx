import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import type { ColumnDef, ColumnFiltersState, SortingState, VisibilityState } from '@tanstack/react-table'
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Columns3,
  FileDown,
  GripVertical,
  Sheet,
} from 'lucide-react'

import { exportarCsv, exportarPdf } from '../lib/exportar'
import { Tooltip, formatoImporte } from './ui'

export type TipoColumna = 'texto' | 'numero' | 'importe' | 'fecha' | 'select'

export interface ColumnaTabla<T> {
  id: string
  encabezado: string
  /** Valor "crudo" para ordenar/filtrar/exportar — no JSX. */
  accessor: (fila: T) => string | number | null | undefined
  /** Si no se da, se pinta el valor de `accessor` tal cual (formateado según `tipo`). */
  render?: (fila: T) => ReactNode
  tipo?: TipoColumna
  /** Para `tipo: 'select'` — qué opciones ofrece el filtro. */
  opciones?: { value: string; label: string }[]
  anchoInicial?: number
  ocultaPorDefecto?: boolean
  ordenable?: boolean
  filtrable?: boolean
}

interface EstadoPersistido {
  columnOrder?: string[]
  columnVisibility?: VisibilityState
  columnSizing?: Record<string, number>
}

function cargarEstado(id: string): EstadoPersistido {
  try {
    const crudo = localStorage.getItem(`tabla:${id}`)
    return crudo ? (JSON.parse(crudo) as EstadoPersistido) : {}
  } catch {
    return {}
  }
}

function guardarEstado(id: string, estado: EstadoPersistido) {
  try {
    localStorage.setItem(`tabla:${id}`, JSON.stringify(estado))
  } catch {
    /* localStorage lleno o bloqueado: la tabla sigue funcionando, solo no recuerda el layout */
  }
}

function filtroRangoFecha(
  row: { getValue: (id: string) => unknown },
  columnId: string,
  filterValue: { desde?: string; hasta?: string },
): boolean {
  const valor = row.getValue(columnId)
  if (valor === null || valor === undefined || valor === '') return false
  const texto = String(valor)
  if (filterValue.desde && texto < filterValue.desde) return false
  if (filterValue.hasta && texto > filterValue.hasta) return false
  return true
}

const TAMANOS_PAGINA = [10, 25, 50, 100]

export function DataTable<T>({
  id,
  columnas,
  datos,
  claveFila,
  vacio,
  nombreExportacion,
}: {
  /** Identificador único de este listado — se usa para recordar el orden,
   *  anchura y columnas visibles en `localStorage` entre sesiones. */
  id: string
  columnas: ColumnaTabla<T>[]
  datos: T[]
  claveFila: (fila: T) => string
  vacio?: ReactNode
  /** Nombre base del fichero al exportar (sin extensión). Por defecto, `id`. */
  nombreExportacion?: string
}) {
  const estadoGuardado = useMemo(() => cargarEstado(id), [id])

  const columnasDef = useMemo<ColumnDef<T>[]>(
    () =>
      columnas.map((col) => ({
        id: col.id,
        accessorFn: col.accessor,
        header: col.encabezado,
        size: col.anchoInicial ?? 160,
        minSize: 60,
        enableSorting: col.ordenable ?? true,
        enableColumnFilter: col.filtrable ?? true,
        // 'select' usa el mismo filtro por subcadena que el texto libre, no
        // 'equals': el desplegable es solo para no tener que adivinar qué
        // valores existen, pero columnas de valor múltiple (p.ej. "roles",
        // varios valores unidos por comas) necesitan "contiene", no "es
        // exactamente igual a" — y para un enum de un solo valor el
        // resultado es el mismo salvo que un valor sea subcadena de otro,
        // cosa que no ocurre con los vocabularios de esta aplicación.
        filterFn: col.tipo === 'fecha' ? filtroRangoFecha : 'includesString',
        cell: (info) => {
          if (col.render) return col.render(info.row.original)
          const valor = info.getValue() as string | number | null | undefined
          if (valor === null || valor === undefined || valor === '') return <span className="muted">—</span>
          if (col.tipo === 'importe') return formatoImporte(valor)
          return String(valor)
        },
      })),
    [columnas],
  )

  const ordenInicial = useMemo(() => {
    const ids = columnas.map((c) => c.id)
    const guardado = (estadoGuardado.columnOrder ?? []).filter((c) => ids.includes(c))
    const faltantes = ids.filter((c) => !guardado.includes(c))
    return [...guardado, ...faltantes]
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const visibilidadInicial = useMemo(() => {
    const base: VisibilityState = {}
    for (const col of columnas) base[col.id] = !col.ocultaPorDefecto
    return { ...base, ...(estadoGuardado.columnVisibility ?? {}) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const [columnOrder, setColumnOrder] = useState<string[]>(ordenInicial)
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(visibilidadInicial)
  const [columnSizing, setColumnSizing] = useState<Record<string, number>>(estadoGuardado.columnSizing ?? {})
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [menuColumnasAbierto, setMenuColumnasAbierto] = useState(false)
  const [arrastrando, setArrastrando] = useState<string | null>(null)

  useEffect(() => {
    guardarEstado(id, { columnOrder, columnVisibility, columnSizing })
  }, [id, columnOrder, columnVisibility, columnSizing])

  // Si `id` cambia sin que el componente se desmonte (p.ej. una misma pantalla
  // que alterna entre dos juegos de columnas distintos por pestañas), hay que
  // recalcular todo el estado — de lo contrario `columnOrder`/`columnFilters`
  // etc. siguen arrastrando ids de la tabla anterior.
  const esPrimerMontaje = useRef(true)
  useEffect(() => {
    if (esPrimerMontaje.current) {
      esPrimerMontaje.current = false
      return
    }
    setColumnOrder(ordenInicial)
    setColumnVisibility(visibilidadInicial)
    setColumnSizing(cargarEstado(id).columnSizing ?? {})
    setSorting([])
    setColumnFilters([])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const table = useReactTable({
    data: datos,
    columns: columnasDef,
    state: { columnOrder, columnVisibility, columnSizing, sorting, columnFilters },
    onColumnOrderChange: setColumnOrder,
    onColumnVisibilityChange: setColumnVisibility,
    onColumnSizingChange: setColumnSizing,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    columnResizeMode: 'onChange',
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 25 } },
  })

  const columnasPorId = useMemo(() => new Map(columnas.map((c) => [c.id, c])), [columnas])
  const filasVisibles = table.getSortedRowModel().rows
  const nombreArchivo = nombreExportacion ?? id

  function datosParaExportar(): { columnas: string[]; filas: string[][] } {
    const cols = table.getVisibleLeafColumns()
    const encabezados = cols.map((c) => columnasPorId.get(c.id)?.encabezado ?? c.id)
    const filas = filasVisibles.map((fila) =>
      cols.map((c) => {
        const def = columnasPorId.get(c.id)
        const valor = def?.accessor(fila.original)
        if (def?.tipo === 'importe' && valor !== null && valor !== undefined) {
          return `${formatoImporte(valor)} €`
        }
        return valor === null || valor === undefined ? '' : String(valor)
      }),
    )
    return { columnas: encabezados, filas }
  }

  return (
    <div className="data-table">
      <div className="data-table__toolbar">
        <div className="data-table__toolbar-menu">
          <Tooltip texto="Elegir qué columnas se ven">
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => setMenuColumnasAbierto((v) => !v)}
            >
              <Columns3 size={14} aria-hidden="true" />
              Columnas
            </button>
          </Tooltip>
          {menuColumnasAbierto && (
            <>
              <div className="data-table__menu-backdrop" onClick={() => setMenuColumnasAbierto(false)} />
              <div className="data-table__menu">
                {table.getAllLeafColumns().map((col) => (
                  <label key={col.id} className="data-table__menu-item">
                    <input
                      type="checkbox"
                      checked={col.getIsVisible()}
                      onChange={col.getToggleVisibilityHandler()}
                    />
                    {columnasPorId.get(col.id)?.encabezado ?? col.id}
                  </label>
                ))}
              </div>
            </>
          )}
        </div>
        <Tooltip texto="Descargar esta tabla como CSV (Excel)">
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => {
              const { columnas: cols, filas } = datosParaExportar()
              exportarCsv(nombreArchivo, cols, filas)
            }}
          >
            <Sheet size={14} aria-hidden="true" />
            CSV
          </button>
        </Tooltip>
        <Tooltip texto="Descargar esta tabla como PDF">
          <button
            type="button"
            className="btn btn--sm"
            onClick={() => {
              const { columnas: cols, filas } = datosParaExportar()
              void exportarPdf(nombreArchivo, nombreArchivo, cols, filas)
            }}
          >
            <FileDown size={14} aria-hidden="true" />
            PDF
          </button>
        </Tooltip>
      </div>

      <div className="table-wrap">
        <table className="table data-table__table" style={{ width: table.getTotalSize() }}>
          <thead>
            <tr>
              {table.getHeaderGroups()[0].headers.map((header) => {
                const def = columnasPorId.get(header.column.id)
                return (
                  <th
                    key={header.id}
                    style={{ width: header.getSize(), position: 'relative' }}
                    className={arrastrando === header.column.id ? 'data-table__th--arrastrando' : ''}
                    draggable
                    onDragStart={() => setArrastrando(header.column.id)}
                    onDragEnd={() => setArrastrando(null)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => {
                      if (!arrastrando || arrastrando === header.column.id) return
                      setColumnOrder((actual) => {
                        const sinOrigen = actual.filter((c) => c !== arrastrando)
                        const destino = sinOrigen.indexOf(header.column.id)
                        sinOrigen.splice(destino, 0, arrastrando)
                        return sinOrigen
                      })
                    }}
                  >
                    <div
                      className="data-table__th-titulo"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <Tooltip texto="Arrastra para reordenar la columna">
                        <span className="data-table__drag-handle">
                          <GripVertical size={14} aria-hidden="true" />
                        </span>
                      </Tooltip>
                      <span>{flexRender(header.column.columnDef.header, header.getContext())}</span>
                      {header.column.getIsSorted() === 'asc' && <ChevronUp size={14} aria-hidden="true" />}
                      {header.column.getIsSorted() === 'desc' && <ChevronDown size={14} aria-hidden="true" />}
                    </div>
                    {header.column.getCanFilter() && (
                      <FiltroColumna
                        tipo={def?.tipo}
                        opciones={def?.opciones}
                        valor={header.column.getFilterValue()}
                        onChange={(v) => header.column.setFilterValue(v)}
                      />
                    )}
                    <div
                      className="data-table__resizer"
                      onMouseDown={header.getResizeHandler()}
                      onTouchStart={header.getResizeHandler()}
                    />
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={claveFila(row.original)}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} style={{ width: cell.column.getSize() }}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {table.getRowModel().rows.length === 0 && (
              <tr>
                <td colSpan={table.getVisibleLeafColumns().length} className="muted">
                  {vacio ?? 'Sin resultados'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="data-table__pie">
        <span className="muted">
          {filasVisibles.length === 0
            ? 'Sin resultados'
            : `${table.getState().pagination.pageIndex * table.getState().pagination.pageSize + 1}–${Math.min(
                (table.getState().pagination.pageIndex + 1) * table.getState().pagination.pageSize,
                filasVisibles.length,
              )} de ${filasVisibles.length}`}
        </span>
        <div className="data-table__pie-controles">
          <select
            className="select"
            style={{ width: 'auto' }}
            value={table.getState().pagination.pageSize}
            onChange={(e) => table.setPageSize(Number(e.target.value))}
          >
            {TAMANOS_PAGINA.map((t) => (
              <option key={t} value={t}>
                {t} / página
              </option>
            ))}
          </select>
          <button className="btn btn--sm" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>
            <ChevronLeft size={14} aria-hidden="true" />
            Anterior
          </button>
          <button className="btn btn--sm" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>
            Siguiente
            <ChevronRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  )
}

function FiltroColumna({
  tipo,
  opciones,
  valor,
  onChange,
}: {
  tipo?: TipoColumna
  opciones?: { value: string; label: string }[]
  valor: unknown
  onChange: (valor: unknown) => void
}) {
  if (tipo === 'fecha') {
    const actual = (valor as { desde?: string; hasta?: string } | undefined) ?? {}
    return (
      <div className="data-table__filtro data-table__filtro--fecha">
        <input
          type="date"
          className="input input--sm"
          value={actual.desde ?? ''}
          onChange={(e) => {
            const desde = e.target.value || undefined
            const siguiente = { ...actual, desde }
            onChange(siguiente.desde || siguiente.hasta ? siguiente : undefined)
          }}
        />
        <input
          type="date"
          className="input input--sm"
          value={actual.hasta ?? ''}
          onChange={(e) => {
            const hasta = e.target.value || undefined
            const siguiente = { ...actual, hasta }
            onChange(siguiente.desde || siguiente.hasta ? siguiente : undefined)
          }}
        />
      </div>
    )
  }

  if (tipo === 'select' && opciones) {
    return (
      <select
        className="select select--sm data-table__filtro"
        value={(valor as string) ?? ''}
        onChange={(e) => onChange(e.target.value || undefined)}
      >
        <option value="">Todos</option>
        {opciones.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    )
  }

  return (
    <input
      className="input input--sm data-table__filtro"
      placeholder="Filtrar…"
      value={(valor as string) ?? ''}
      onChange={(e) => onChange(e.target.value || undefined)}
    />
  )
}
