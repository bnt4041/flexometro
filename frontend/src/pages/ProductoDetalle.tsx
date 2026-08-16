import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { CamposLibres } from '../components/CamposLibres'
import { Checkbox, EmptyState, ErrorNotice, Field, Modal, ModalPantalla, formatoImporte } from '../components/ui'
import { ETIQUETA_IVA, ETIQUETA_TIPO_PRODUCTO, api } from '../lib/api'
import type { PrecioSuministro, ProductoDetalle as Detalle, Tercero } from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'
import { useContextoProductos } from './Productos'

export function ProductoDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoProductos()
  const [producto, setProducto] = useState<Detalle | null>(null)
  const [borrador, setBorrador] = useState<Partial<Detalle>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [nuevaTarifa, setNuevaTarifa] = useState(false)
  const unidadesMedida = useDiccionario('unidad_medida')

  const cargar = useCallback(async () => {
    try {
      const datos = await api.productos.get(id)
      setProducto(datos)
      setBorrador({})
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/productos')
  }

  if (error && !producto) {
    return (
      <ModalPantalla title="Producto" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!producto) return null

  const valor = <K extends keyof Detalle>(campo: K): Detalle[K] =>
    (borrador[campo] ?? producto[campo]) as Detalle[K]
  const cambiar = <K extends keyof Detalle>(campo: K, v: Detalle[K]) =>
    setBorrador((b) => ({ ...b, [campo]: v }))
  const hayCambios = Object.keys(borrador).length > 0

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.productos.update(id, borrador)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar «${producto!.resumen}»? No se puede deshacer.`)) return
    try {
      await api.productos.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <ModalPantalla
      title={
        <>
          {producto.resumen} <span className="table__code">{producto.codigo}</span>
        </>
      }
      onClose={cerrar}
    >
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          {ETIQUETA_TIPO_PRODUCTO[producto.tipo]} · origen del dato: {producto.origen_dato}
        </p>
        <button className="btn btn--danger" onClick={() => void eliminar()}>
          Eliminar
        </button>
      </div>

      <ErrorNotice error={error} />

      <div className="card">
        <div className="form-section">
          <div className="form-section__title">Ficha</div>
          <div className="form-grid">
            <Field label="Descripción corta">
              <input
                className="input"
                value={valor('resumen')}
                onChange={(e) => cambiar('resumen', e.target.value)}
              />
            </Field>
            <Field label="Tipo">
              <select
                className="select"
                value={valor('tipo')}
                onChange={(e) => cambiar('tipo', e.target.value as Detalle['tipo'])}
              >
                {Object.entries(ETIQUETA_TIPO_PRODUCTO).map(([clave, etiqueta]) => (
                  <option key={clave} value={clave}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Unidad">
              <select className="select" value={valor('unidad')} onChange={(e) => cambiar('unidad', e.target.value)}>
                {unidadesMedida.map((u) => (
                  <option key={u.clave} value={u.clave}>
                    {u.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Tipo de IVA">
              <select
                className="select"
                value={valor('tipo_iva')}
                onChange={(e) => cambiar('tipo_iva', e.target.value as Detalle['tipo_iva'])}
              >
                {Object.entries(ETIQUETA_IVA).map(([clave, etiqueta]) => (
                  <option key={clave} value={clave}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Precio de venta">
              <input
                className="input"
                type="number"
                step="0.01"
                value={valor('precio_venta') ?? ''}
                onChange={(e) => cambiar('precio_venta', e.target.value || null)}
              />
            </Field>
            <Field label="EAN">
              <input
                className="input"
                value={valor('ean') ?? ''}
                onChange={(e) => cambiar('ean', e.target.value || null)}
              />
            </Field>
          </div>
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <Field label="Descripción larga">
              <textarea
                className="input"
                value={valor('descripcion') ?? ''}
                onChange={(e) => cambiar('descripcion', e.target.value || null)}
              />
            </Field>
          </div>
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <Checkbox
              label="Activo"
              checked={valor('activo')}
              onChange={(v) => cambiar('activo', v)}
            />
          </div>
        </div>

        <div className="form-actions">
          <button className="btn" disabled={!hayCambios} onClick={() => setBorrador({})}>
            Descartar
          </button>
          <button
            className="btn btn--primary"
            disabled={!hayCambios || guardando}
            onClick={() => void guardar()}
          >
            {guardando ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>

      <CamposLibres entidad="producto" entidadId={id} />

      <div className="page-head" style={{ marginTop: 'var(--sp-6)' }}>
        <div>
          <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Tarifas de proveedor</h2>
          <p className="page-lead">
            Precio de suministro: producto + proveedor + fecha. Se guarda con cuatro decimales
            porque las tarifas llegan así; el redondeo a dos se aplica al encadenar conceptos.
          </p>
        </div>
        <button className="btn" onClick={() => setNuevaTarifa(true)}>
          Añadir tarifa
        </button>
      </div>

      <div className="table-wrap">
        {producto.suministros.length === 0 ? (
          <EmptyState title="Sin tarifas">
            Añade el precio de al menos un proveedor para que este producto pueda alimentar un
            precio básico.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Proveedor</th>
                <th className="table__num">Precio</th>
                <th className="table__num">Dto.</th>
                <th className="table__num">Neto</th>
                <th>Vigencia</th>
                <th>Ref.</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {producto.suministros.map((s) => (
                <FilaTarifa key={s.id} tarifa={s} onCambio={cargar} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {nuevaTarifa && (
        <NuevaTarifaModal
          productoId={id}
          onClose={() => setNuevaTarifa(false)}
          onCreada={() => {
            setNuevaTarifa(false)
            void cargar()
          }}
        />
      )}
    </ModalPantalla>
  )
}

function FilaTarifa({
  tarifa,
  onCambio,
}: {
  tarifa: PrecioSuministro
  onCambio: () => void
}) {
  const [error, setError] = useState<string | null>(null)

  async function marcarPreferente() {
    try {
      await api.suministros.update(tarifa.id, { es_preferente: true })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar() {
    if (!window.confirm('¿Eliminar esta tarifa?')) return
    await api.suministros.remove(tarifa.id)
    onCambio()
  }

  return (
    <tr>
      <td>
        {tarifa.proveedor_razon_social ?? <span className="muted">—</span>}
        {tarifa.es_preferente && <span className="chip chip--preferente"> preferente</span>}
        {error && <div className="muted">{error}</div>}
      </td>
      <td className="table__num">{formatoImporte(tarifa.precio, 4)}</td>
      <td className="table__num">{formatoImporte(tarifa.descuento)} %</td>
      <td className="table__num">
        <strong>{formatoImporte(tarifa.precio_neto, 4)}</strong>
      </td>
      <td>
        {tarifa.vigente_desde}
        {tarifa.vigente_hasta ? ` → ${tarifa.vigente_hasta}` : ''}
      </td>
      <td className="table__code">{tarifa.referencia_proveedor ?? '—'}</td>
      <td className="table__actions">
        {!tarifa.es_preferente && (
          <button className="btn btn--sm" onClick={() => void marcarPreferente()}>
            Preferente
          </button>
        )}{' '}
        <button className="btn btn--sm btn--danger" onClick={() => void eliminar()}>
          Eliminar
        </button>
      </td>
    </tr>
  )
}

function NuevaTarifaModal({
  productoId,
  onClose,
  onCreada,
}: {
  productoId: string
  onClose: () => void
  onCreada: () => void
}) {
  const [proveedores, setProveedores] = useState<Tercero[]>([])
  const [proveedorId, setProveedorId] = useState('')
  const [precio, setPrecio] = useState('')
  const [descuento, setDescuento] = useState('0')
  const [vigenteDesde, setVigenteDesde] = useState(new Date().toISOString().slice(0, 10))
  const [referencia, setReferencia] = useState('')
  const [esPreferente, setEsPreferente] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api.terceros
      .list({ rol: 'proveedor', activo: true, limit: 500 })
      .then((page) => {
        setProveedores(page.items)
        if (page.items.length > 0) setProveedorId(page.items[0].id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  async function guardar() {
    setError(null)
    try {
      await api.productos.addSuministro(productoId, {
        proveedor_id: proveedorId,
        precio,
        descuento,
        vigente_desde: vigenteDesde,
        referencia_proveedor: referencia || null,
        es_preferente: esPreferente,
      })
      onCreada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Nueva tarifa de proveedor" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        {proveedores.length === 0 ? (
          <EmptyState title="No hay proveedores">
            Marca antes algún tercero con el rol de proveedor.
          </EmptyState>
        ) : (
          <>
            <div className="form-grid">
              <Field label="Proveedor">
                <select
                  className="select"
                  value={proveedorId}
                  onChange={(e) => setProveedorId(e.target.value)}
                >
                  {proveedores.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.razon_social}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Precio" hint="Hasta cuatro decimales">
                <input
                  className="input"
                  type="number"
                  step="0.0001"
                  value={precio}
                  onChange={(e) => setPrecio(e.target.value)}
                />
              </Field>
              <Field label="Descuento (%)">
                <input
                  className="input"
                  type="number"
                  step="0.01"
                  value={descuento}
                  onChange={(e) => setDescuento(e.target.value)}
                />
              </Field>
              <Field label="Vigente desde">
                <input
                  className="input"
                  type="date"
                  value={vigenteDesde}
                  onChange={(e) => setVigenteDesde(e.target.value)}
                />
              </Field>
              <Field label="Referencia del proveedor">
                <input
                  className="input"
                  value={referencia}
                  onChange={(e) => setReferencia(e.target.value)}
                />
              </Field>
            </div>
            <div style={{ marginTop: 'var(--sp-4)' }}>
              <Checkbox
                label="Marcar como tarifa preferente"
                checked={esPreferente}
                onChange={setEsPreferente}
              />
            </div>
          </>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={proveedorId === '' || precio === ''}
          onClick={() => void guardar()}
        >
          Crear
        </button>
      </div>
    </Modal>
  )
}
