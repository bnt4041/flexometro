import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'

import { EmptyState, ErrorNotice, Field, ModalPantalla, formatoImporte } from '../components/ui'
import { DataTable } from '../components/DataTable'
import type { ColumnaTabla } from '../components/DataTable'
import {
  ETIQUETA_NATURALEZA,
  ETIQUETA_ORIGEN_PRECIO,
  ETIQUETA_TIPO_CONCEPTO,
  api,
} from '../lib/api'
import type { Concepto, NaturalezaConcepto, Producto, TipoConcepto } from '../lib/api'

// El listado ya no pagina en el servidor: el `DataTable` pagina, ordena y
// filtra en el navegador sobre este lote — 500 es el máximo que admite el
// endpoint (`le=500`).
const LIMITE = 500

export type ContextoPrecios = { onCambio: () => void }

export function useContextoPrecios() {
  return useOutletContext<ContextoPrecios>()
}

export function Precios() {
  const [items, setItems] = useState<Concepto[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const page = await api.conceptos.list({ limit: LIMITE })
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

  const columnas = useMemo<ColumnaTabla<Concepto>[]>(
    () => [
      { id: 'codigo', encabezado: 'Código', accessor: (c) => c.codigo, anchoInicial: 110 },
      {
        id: 'resumen',
        encabezado: 'Descripción',
        accessor: (c) => c.resumen,
        render: (c) => (
          <>
            <Link className="table__link" to={`${c.id}`}>
              {c.resumen}
            </Link>
            {!c.activo && <span className="chip chip--inactivo"> inactivo</span>}
          </>
        ),
        anchoInicial: 280,
      },
      {
        id: 'tipo',
        encabezado: 'Nivel',
        accessor: (c) => c.tipo,
        render: (c) => <span className={`chip chip--${c.tipo}`}>{ETIQUETA_TIPO_CONCEPTO[c.tipo]}</span>,
        tipo: 'select',
        opciones: Object.entries(ETIQUETA_TIPO_CONCEPTO).map(([value, label]) => ({ value, label })),
        anchoInicial: 120,
      },
      { id: 'unidad', encabezado: 'Ud.', accessor: (c) => c.unidad, anchoInicial: 70 },
      {
        id: 'precio',
        encabezado: 'Precio',
        accessor: (c) => c.precio,
        render: (c) => <strong>{formatoImporte(c.precio)}</strong>,
        tipo: 'importe',
        anchoInicial: 110,
      },
      {
        id: 'origen_precio',
        encabezado: 'Precio según',
        accessor: (c) => ETIQUETA_ORIGEN_PRECIO[c.origen_precio],
        anchoInicial: 140,
      },
    ],
    [],
  )

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Cuadro de precios</h1>
          <p className="page-lead">
            Básicos, auxiliares y unitarios son el mismo objeto en distinto nivel del árbol.
            Cambiar un precio propaga hacia arriba a todo lo que lo contiene.
          </p>
        </div>
        <Link className="btn btn--primary" to="nuevo">
          Nuevo concepto
        </Link>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="Sin resultados">
          Empieza por los básicos: mano de obra, materiales y maquinaria.
        </EmptyState>
      ) : (
        <DataTable
          id="precios"
          columnas={columnas}
          datos={items}
          claveFila={(c) => c.id}
          vacio="Sin resultados con estos filtros"
        />
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoPrecios} />
    </>
  )
}

export function ConceptoCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoPrecios()
  const [tipo, setTipo] = useState<TipoConcepto>('basico')
  const [resumen, setResumen] = useState('')
  const [unidad, setUnidad] = useState('ud')
  const [naturaleza, setNaturaleza] = useState<NaturalezaConcepto>('material')
  const [origenPrecio, setOrigenPrecio] = useState<'manual' | 'producto'>('manual')
  const [precio, setPrecio] = useState('0.00')
  const [productoId, setProductoId] = useState('')
  const [costesIndirectos, setCostesIndirectos] = useState('')
  const [productos, setProductos] = useState<Producto[]>([])
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  function cerrar() {
    navigate('/precios')
  }

  useEffect(() => {
    if (origenPrecio !== 'producto' || productos.length > 0) return
    void api.productos
      .list({ activo: true, limit: 500 })
      .then((page) => {
        setProductos(page.items)
        if (page.items.length > 0) setProductoId(page.items[0].id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [origenPrecio, productos.length])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.conceptos.create({
        tipo,
        resumen,
        unidad,
        naturaleza,
        origen_precio: origenPrecio,
        precio: origenPrecio === 'manual' ? precio : '0.00',
        producto_id: origenPrecio === 'producto' ? productoId : null,
        costes_indirectos: tipo === 'unitario' && costesIndirectos ? costesIndirectos : null,
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
    <ModalPantalla title="Nuevo concepto" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
        <div className="form-grid">
          <Field
            label="Nivel"
            hint={
              tipo === 'basico'
                ? 'Recurso elemental: mano de obra, material, maquinaria'
                : tipo === 'auxiliar'
                  ? 'Se compone de básicos y entra en los unitarios'
                  : 'La partida que se presupuesta'
            }
          >
            <select
              className="select"
              value={tipo}
              onChange={(e) => setTipo(e.target.value as TipoConcepto)}
            >
              {Object.entries(ETIQUETA_TIPO_CONCEPTO).map(([clave, etiqueta]) => (
                <option key={clave} value={clave}>
                  {etiqueta}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Descripción corta">
            <input
              className="input"
              value={resumen}
              onChange={(e) => setResumen(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Unidad">
            <input className="input" value={unidad} onChange={(e) => setUnidad(e.target.value)} />
          </Field>
          <Field label="Naturaleza" hint="Equivale al campo TIPO de FIEBDC-3">
            <select
              className="select"
              value={naturaleza}
              onChange={(e) => setNaturaleza(e.target.value as NaturalezaConcepto)}
            >
              {Object.entries(ETIQUETA_NATURALEZA).map(([clave, etiqueta]) => (
                <option key={clave} value={clave}>
                  {etiqueta}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
          <Field
            label="Precio"
            hint="Si lo descompones después, pasa a calcularse solo"
          >
            <select
              className="select"
              value={origenPrecio}
              onChange={(e) => setOrigenPrecio(e.target.value as 'manual' | 'producto')}
            >
              <option value="manual">A mano</option>
              <option value="producto">Desde el catálogo</option>
            </select>
          </Field>

          {origenPrecio === 'manual' ? (
            <Field label="Importe">
              <input
                className="input"
                type="number"
                step="0.01"
                value={precio}
                onChange={(e) => setPrecio(e.target.value)}
              />
            </Field>
          ) : (
            <Field label="Producto" hint="Toma la tarifa preferente del proveedor">
              <select
                className="select"
                value={productoId}
                onChange={(e) => setProductoId(e.target.value)}
              >
                {productos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.codigo} · {p.resumen}
                  </option>
                ))}
              </select>
            </Field>
          )}

          {tipo === 'unitario' && (
            <Field label="Costes indirectos (%)" hint="Se aplica sobre el coste directo">
              <input
                className="input"
                type="number"
                step="0.01"
                value={costesIndirectos}
                onChange={(e) => setCostesIndirectos(e.target.value)}
              />
            </Field>
          )}
        </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || resumen.trim() === ''}
            onClick={() => void guardar()}
          >
            {guardando ? 'Guardando…' : 'Crear'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
