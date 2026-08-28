/** Pestaña «Compras» de la obra: lo que entra y lo que nos facturan.
 *
 *  Dos tablas y un cuadre. Los albaranes son la entrega física; las facturas
 *  recibidas, lo que hay que pagar. Lo que de verdad interesa es la diferencia
 *  entre ambas: material que entró y nadie ha facturado todavía, o una factura
 *  sin entrega detrás.
 *
 *  Se compone aquí, en el frontend, y no en un endpoint: `compras` y
 *  `facturacion` son módulos hermanos y ninguno ve al otro
 *  (`ModuleRegistry._detect_cycles()`), así que la vista que cruza compras y
 *  ventas solo puede armarse desde el navegador, que sí lo ve todo.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Plus, Trash2, X } from 'lucide-react'

import { ETIQUETA_ESTADO_ALBARAN, ETIQUETA_IVA, api } from '../lib/api'
import type {
  AlbaranResumen,
  FacturaRecibida,
  TipoIVA,
  TotalesComprasObra,
} from '../lib/api'
import { EmptyState, ErrorNotice, Field, Modal, Tooltip, formatoImporte } from './ui'

export function ComprasObra({ obraId }: { obraId: string }) {
  const [albaranes, setAlbaranes] = useState<AlbaranResumen[]>([])
  const [facturas, setFacturas] = useState<FacturaRecibida[]>([])
  const [totales, setTotales] = useState<TotalesComprasObra | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [registrando, setRegistrando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const [alb, fac, tot] = await Promise.all([
        api.albaranes.list({ obra_id: obraId, tipo: 'proveedor', limit: 200 }),
        api.facturasRecibidas.list({ obra_id: obraId, limit: 200 }),
        api.facturasRecibidas.totalesDeObra(obraId),
      ])
      setAlbaranes(alb.items)
      setFacturas(fac.items)
      setTotales(tot)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [obraId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function cambiarEstado(factura: FacturaRecibida) {
    try {
      await api.facturasRecibidas.update(factura.id, {
        estado: factura.estado === 'pagada' ? 'pendiente' : 'pagada',
      })
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar(factura: FacturaRecibida) {
    if (
      !window.confirm(
        `¿Eliminar el registro de la factura ${factura.numero_proveedor} de ` +
          `${factura.proveedor_razon_social}?`,
      )
    ) {
      return
    }
    try {
      await api.facturasRecibidas.remove(factura.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  // Qué albaranes no aparecen en ninguna factura. El servidor da el número en
  // el cuadre; aquí se necesita el conjunto para marcar las filas.
  const facturados = new Set(facturas.flatMap((f) => f.albaran_ids))

  return (
    <div className="form-section">
      <ErrorNotice error={error} />

      {totales && (
        <div className="cuadre">
          <div className="cuadre__dato">
            <span className="cuadre__etiqueta">Entregado (albaranes)</span>
            <strong>{formatoImporte(totales.albaranes_total)} €</strong>
          </div>
          <div className="cuadre__dato">
            <span className="cuadre__etiqueta">Facturado (base)</span>
            <strong>{formatoImporte(totales.facturas_base)} €</strong>
          </div>
          <div className="cuadre__dato">
            <span className="cuadre__etiqueta">Pendiente de pago</span>
            <strong className={Number(totales.pendiente_de_pago) > 0 ? 'cuadre--ojo' : undefined}>
              {formatoImporte(totales.pendiente_de_pago)} €
            </strong>
          </div>
          <div className="cuadre__dato">
            <span className="cuadre__etiqueta">Albaranes sin facturar</span>
            <strong className={totales.albaranes_sin_facturar > 0 ? 'cuadre--ojo' : undefined}>
              {totales.albaranes_sin_facturar}
            </strong>
          </div>
        </div>
      )}

      <div className="page-head">
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Albaranes recibidos</h2>
      </div>

      <div className="table-wrap">
        {albaranes.length === 0 ? (
          <EmptyState title="Sin albaranes">
            Los albaranes se registran desde el módulo de Compras, indicando esta obra.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Albarán</th>
                <th>Proveedor</th>
                <th>Fecha</th>
                <th>Estado</th>
                <th className="table__num">Importe</th>
                <th>Facturado</th>
              </tr>
            </thead>
            <tbody>
              {albaranes.map((a) => (
                <tr key={a.id}>
                  <td>
                    <Link to={`/albaranes/${a.id}`}>{a.codigo}</Link>
                    {a.numero_proveedor && (
                      <div className="table__code">nº {a.numero_proveedor}</div>
                    )}
                  </td>
                  <td>{a.tercero_razon_social}</td>
                  <td>{a.fecha}</td>
                  <td>
                    <span className={`chip chip--estado-${a.estado}`}>
                      {ETIQUETA_ESTADO_ALBARAN[a.estado]}
                    </span>
                  </td>
                  <td className="table__num">{formatoImporte(a.total)} €</td>
                  <td>
                    {facturados.has(a.id) ? (
                      <span className="muted">Sí</span>
                    ) : (
                      <Tooltip texto="Entregado pero todavía sin factura del proveedor">
                        <span className="chip chip--vinculo-anexo">Pendiente</span>
                      </Tooltip>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="page-head" style={{ marginTop: 'var(--sp-6)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Facturas de proveedor</h2>
        <Tooltip texto="Registrar una factura recibida de un proveedor">
          <button className="btn" onClick={() => setRegistrando(true)}>
            <Plus size={16} aria-hidden="true" />
            Registrar factura
          </button>
        </Tooltip>
      </div>

      <div className="table-wrap">
        {facturas.length === 0 ? (
          <EmptyState title="Sin facturas de proveedor">
            Registra las facturas que te lleguen para controlar lo que queda por pagar y cuadrarlo
            con los albaranes.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Factura</th>
                <th>Proveedor</th>
                <th>Fecha</th>
                <th>Vence</th>
                <th className="table__num">Base</th>
                <th>IVA</th>
                <th className="table__num">Total</th>
                <th>Cubre</th>
                <th>Estado</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {facturas.map((f) => (
                <tr key={f.id}>
                  <td>
                    <strong>{f.numero_proveedor}</strong>
                    <div className="table__code">{f.codigo}</div>
                  </td>
                  <td>{f.proveedor_razon_social}</td>
                  <td>{f.fecha}</td>
                  <td>{f.fecha_vencimiento ?? <span className="muted">—</span>}</td>
                  <td className="table__num">{formatoImporte(f.base_imponible)} €</td>
                  <td>
                    {f.inversion_sujeto_pasivo ? (
                      <Tooltip texto="Inversión del sujeto pasivo: el IVA lo autorrepercutimos nosotros">
                        <span className="muted">ISP</span>
                      </Tooltip>
                    ) : (
                      ETIQUETA_IVA[f.tipo_iva]
                    )}
                  </td>
                  <td className="table__num">
                    <strong>{formatoImporte(f.total)} €</strong>
                  </td>
                  <td>
                    {f.albaran_codigos.length === 0 ? (
                      <span className="muted">—</span>
                    ) : (
                      <span className="table__code">{f.albaran_codigos.join(', ')}</span>
                    )}
                  </td>
                  <td>
                    <span
                      className={`chip chip--estado-${f.estado === 'pagada' ? 'aprobado' : 'borrador'}`}
                    >
                      {f.estado === 'pagada' ? `Pagada ${f.fecha_pago ?? ''}` : 'Pendiente'}
                    </span>
                  </td>
                  <td className="table__actions">
                    <Tooltip texto={f.estado === 'pagada' ? 'Marcar como pendiente' : 'Marcar como pagada'}>
                      <button className="btn btn--sm" onClick={() => void cambiarEstado(f)}>
                        {f.estado === 'pagada' ? <X size={14} /> : <Check size={14} />}
                      </button>
                    </Tooltip>
                    <Tooltip texto="Eliminar el registro">
                      <button className="btn btn--sm" onClick={() => void eliminar(f)}>
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </Tooltip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {registrando && (
        <RegistrarFacturaModal
          obraId={obraId}
          albaranes={albaranes}
          onClose={() => setRegistrando(false)}
          onRegistrada={() => {
            setRegistrando(false)
            void cargar()
          }}
        />
      )}
    </div>
  )
}

function RegistrarFacturaModal({
  obraId,
  albaranes,
  onClose,
  onRegistrada,
}: {
  obraId: string
  albaranes: AlbaranResumen[]
  onClose: () => void
  onRegistrada: () => void
}) {
  const hoy = new Date().toISOString().slice(0, 10)
  const [proveedorId, setProveedorId] = useState('')
  const [numero, setNumero] = useState('')
  const [fecha, setFecha] = useState(hoy)
  const [vencimiento, setVencimiento] = useState('')
  const [base, setBase] = useState('')
  const [tipoIva, setTipoIva] = useState<TipoIVA>('general')
  const [isp, setIsp] = useState(false)
  const [total, setTotal] = useState('')
  const [cubre, setCubre] = useState<string[]>([])
  const [notas, setNotas] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  // Los proveedores salen de los albaranes de la obra: es de quien se recibe
  // material, y así no hay que cargar el fichero entero de terceros.
  // `albaranes` aquí siempre es de tipo=proveedor (así se pidió la lista),
  // `proveedor_id` nunca es null en la práctica.
  const proveedores = [...new Map(albaranes.map((a) => [a.proveedor_id!, a.tercero_razon_social]))]

  const listo = proveedorId !== '' && numero.trim() !== '' && base.trim() !== ''

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.facturasRecibidas.create({
        obra_id: obraId,
        proveedor_id: proveedorId,
        numero_proveedor: numero.trim(),
        fecha,
        fecha_vencimiento: vencimiento || null,
        base_imponible: base.trim(),
        tipo_iva: tipoIva,
        inversion_sujeto_pasivo: isp,
        // Vacío = que lo calcule el servidor. Si se teclea, manda el papel.
        total: total.trim() || null,
        albaran_ids: cubre,
        notas: notas.trim() || null,
      })
      onRegistrada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title="Registrar factura de proveedor" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        {proveedores.length === 0 && (
          <p className="muted">
            Esta obra no tiene albaranes todavía, así que no hay proveedores de los que partir.
            Registra primero un albarán.
          </p>
        )}
        <div className="form-grid">
          <Field label="Proveedor">
            <select
              className="select"
              value={proveedorId}
              onChange={(e) => setProveedorId(e.target.value)}
              autoFocus
            >
              <option value="">Elige…</option>
              {proveedores.map(([pid, nombre]) => (
                <option key={pid} value={pid}>
                  {nombre}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Nº de factura" hint="El número que trae la factura del proveedor">
            <input
              className="input"
              value={numero}
              onChange={(e) => setNumero(e.target.value)}
              placeholder="F/2026/118"
            />
          </Field>
          <Field label="Fecha">
            <input
              className="input"
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </Field>
          <Field label="Vencimiento">
            <input
              className="input"
              type="date"
              value={vencimiento}
              onChange={(e) => setVencimiento(e.target.value)}
            />
          </Field>
          <Field label="Base imponible">
            <input
              className="input"
              inputMode="decimal"
              value={base}
              onChange={(e) => setBase(e.target.value)}
            />
          </Field>
          <Field label="IVA">
            <select
              className="select"
              value={tipoIva}
              disabled={isp}
              onChange={(e) => setTipoIva(e.target.value as TipoIVA)}
            >
              {(Object.keys(ETIQUETA_IVA) as TipoIVA[]).map((t) => (
                <option key={t} value={t}>
                  {ETIQUETA_IVA[t]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Total" hint="Déjalo vacío para que se calcule; si el proveedor redondea distinto, tecléalo">
            <input
              className="input"
              inputMode="decimal"
              value={total}
              onChange={(e) => setTotal(e.target.value)}
            />
          </Field>
        </div>

        <label className="checkbox">
          <input type="checkbox" checked={isp} onChange={(e) => setIsp(e.target.checked)} />
          Inversión del sujeto pasivo (llega sin IVA y lo autorrepercutimos)
        </label>

        {albaranes.length > 0 && (
          <Field label="Albaranes que cubre" hint="Es lo que permite cuadrar lo entregado con lo facturado">
            <div className="lista-marcable">
              {albaranes.map((a) => (
                <label key={a.id} className="checkbox">
                  <input
                    type="checkbox"
                    checked={cubre.includes(a.id)}
                    onChange={(e) =>
                      setCubre((actuales) =>
                        e.target.checked
                          ? [...actuales, a.id]
                          : actuales.filter((x) => x !== a.id),
                      )
                    }
                  />
                  {a.codigo} · {a.fecha} · {formatoImporte(a.total)} €
                </label>
              ))}
            </div>
          </Field>
        )}

        <Field label="Notas">
          <input className="input" value={notas} onChange={(e) => setNotas(e.target.value)} />
        </Field>
      </div>

      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={!listo || guardando}
          onClick={() => void guardar()}
        >
          {!guardando && <Check size={16} aria-hidden="true" />}
          {guardando ? 'Registrando…' : 'Registrar'}
        </button>
      </div>
    </Modal>
  )
}
