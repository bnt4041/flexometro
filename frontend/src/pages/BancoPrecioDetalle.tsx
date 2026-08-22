import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Plus, Save, Star, Trash2, X } from 'lucide-react'

import { CamposLibres } from '../components/CamposLibres'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import {
  Checkbox,
  EmptyState,
  ErrorNotice,
  Field,
  Modal,
  ModalPantalla,
  Tooltip,
  formatoImporte,
} from '../components/ui'
import {
  ETIQUETA_IVA,
  ETIQUETA_NATURALEZA,
  ETIQUETA_ORIGEN_PRECIO,
  ETIQUETA_TIPO_CONCEPTO,
  api,
} from '../lib/api'
import type {
  Concepto,
  ConceptoDetalle as Detalle,
  Familia,
  HistoricoPrecio,
  Linea,
  PartidaUso,
  PrecioSuministro,
  Tercero,
  Uso,
  Ventas,
} from '../lib/api'
import { useDiccionario } from '../lib/useDiccionario'
import { useContextoBancoPrecios } from './BancoPrecios'

function formatoFecha(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
}

export function BancoPrecioDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoBancoPrecios()
  const unidadesMedida = useDiccionario('unidad_medida')
  const [concepto, setConcepto] = useState<Detalle | null>(null)
  const [enDescomposiciones, setEnDescomposiciones] = useState<Uso[]>([])
  const [enPartidas, setEnPartidas] = useState<PartidaUso[]>([])
  const [historico, setHistorico] = useState<HistoricoPrecio[]>([])
  const [ventas, setVentas] = useState<Ventas | null>(null)
  const [ventasDisponibles, setVentasDisponibles] = useState(true)
  const [familias, setFamilias] = useState<Familia[]>([])
  const [borrador, setBorrador] = useState<Partial<Detalle>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [anadiendoLinea, setAnadiendoLinea] = useState(false)
  const [nuevaTarifa, setNuevaTarifa] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const [datos, usos, historicoDatos, familiasDatos] = await Promise.all([
        api.conceptos.get(id),
        api.conceptos.dondeSeUsa(id),
        api.conceptos.historico(id),
        api.familias.list(),
      ])
      setConcepto(datos)
      setEnDescomposiciones(usos.en_descomposiciones)
      setEnPartidas(usos.en_partidas)
      setHistorico(historicoDatos)
      setFamilias(familiasDatos)
      setBorrador({})
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
    // "Ventas" vive en el módulo de facturación: si no está activo, el
    // endpoint no existe y la ficha simplemente no enseña esa sección.
    try {
      setVentas(await api.conceptos.ventas(id))
      setVentasDisponibles(true)
    } catch {
      setVentasDisponibles(false)
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/banco-precios')
  }

  if (error && !concepto) {
    return (
      <ModalPantalla title="Ficha del banco de precios" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!concepto) return null

  const valor = <K extends keyof Detalle>(campo: K): Detalle[K] =>
    (borrador[campo] ?? concepto[campo]) as Detalle[K]
  const cambiar = <K extends keyof Detalle>(campo: K, v: Detalle[K]) =>
    setBorrador((b) => ({ ...b, [campo]: v }))
  const hayCambios = Object.keys(borrador).length > 0
  const calculado = concepto.origen_precio === 'descomposicion'

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.conceptos.update(id, borrador)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar «${concepto!.resumen}»?`)) return
    try {
      await api.conceptos.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const pestanaFicha = (
    <>
      <ErrorNotice error={error} />

      <div className="card">
        <div className="form-section">
          <div className="form-section__title">Ficha</div>
          <div className="form-grid">
            <Field ancho="doble" label="Descripción corta">
              <input
                className="input"
                value={valor('resumen')}
                onChange={(e) => cambiar('resumen', e.target.value)}
              />
            </Field>
            <Field label="Unidad">
              <select
                className="select"
                value={valor('unidad')}
                onChange={(e) => cambiar('unidad', e.target.value)}
              >
                {unidadesMedida.map((u) => (
                  <option key={u.clave} value={u.clave}>
                    {u.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Naturaleza">
              <select
                className="select"
                value={valor('naturaleza')}
                onChange={(e) => cambiar('naturaleza', e.target.value as Detalle['naturaleza'])}
              >
                {Object.entries(ETIQUETA_NATURALEZA).map(([clave, etiqueta]) => (
                  <option key={clave} value={clave}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Precio de coste"
              hint={
                calculado
                  ? 'Lo fija el descompuesto'
                  : concepto.origen_precio === 'producto'
                    ? 'Lo fija la tarifa de proveedor preferente'
                    : undefined
              }
            >
              <input
                className="input"
                type="number"
                step="0.01"
                disabled={concepto.origen_precio !== 'manual'}
                value={valor('precio')}
                onChange={(e) => cambiar('precio', e.target.value)}
              />
            </Field>
            <Field label="Precio de venta" hint="Distinto del precio de coste; nadie lo toca solo">
              <input
                className="input"
                type="number"
                step="0.01"
                value={valor('precio_venta') ?? ''}
                onChange={(e) => cambiar('precio_venta', e.target.value || null)}
              />
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
            <Field label="EAN">
              <input
                className="input"
                value={valor('ean') ?? ''}
                onChange={(e) => cambiar('ean', e.target.value || null)}
              />
            </Field>
            <Field label="Familia">
              <select
                className="select"
                value={valor('familia_id') ?? ''}
                onChange={(e) => cambiar('familia_id', e.target.value || null)}
              >
                <option value="">Sin familia</option>
                {familias.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.nombre}
                  </option>
                ))}
              </select>
            </Field>
            {concepto.tipo === 'unitario' && (
              <Field label="Costes indirectos (%)">
                <input
                  className="input"
                  type="number"
                  step="0.01"
                  value={valor('costes_indirectos') ?? ''}
                  onChange={(e) => cambiar('costes_indirectos', e.target.value || null)}
                />
              </Field>
            )}
          </div>
          <div style={{ marginTop: 'var(--sp-4)' }}>
            <Field ancho="completo" label="Descripción larga">
              <textarea
                className="input"
                value={valor('texto') ?? ''}
                onChange={(e) => cambiar('texto', e.target.value || null)}
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
            <X size={16} aria-hidden="true" />
            Descartar
          </button>
          <button
            className="btn btn--primary"
            disabled={!hayCambios || guardando}
            onClick={() => void guardar()}
          >
            {!guardando && <Save size={16} aria-hidden="true" />}
            {guardando ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>

      <CamposLibres entidad="concepto" entidadId={id} />
    </>
  )

  const pestanaDescompuesto = (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          Cada importe se redondea a dos decimales antes de sumar, como en Presto: así el
          descompuesto impreso cuadra columna a columna.
        </p>
        <button className="btn" onClick={() => setAnadiendoLinea(true)}>
          <Plus size={16} aria-hidden="true" />
          Añadir línea
        </button>
      </div>

      <div className="table-wrap">
        {concepto.lineas.length === 0 ? (
          <EmptyState title="Sin descomponer">
            Este concepto tiene precio propio. En cuanto le añadas una línea, su precio pasará a
            calcularse a partir de los hijos.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Descripción</th>
                <th>Ud.</th>
                <th className="table__num">Rendimiento</th>
                <th className="table__num">Precio</th>
                <th className="table__num">Importe</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {concepto.lineas.map((linea) => (
                <FilaLinea key={linea.id} linea={linea} onCambio={cargar} />
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={5} className="table__num total-label">
                  Coste directo
                </td>
                <td className="table__num">
                  <strong>{formatoImporte(concepto.coste_directo)}</strong>
                </td>
                <td />
              </tr>
              {concepto.costes_indirectos && (
                <tr>
                  <td colSpan={5} className="table__num total-label">
                    Costes indirectos {formatoImporte(concepto.costes_indirectos)} %
                  </td>
                  <td className="table__num">
                    {formatoImporte(
                      String(Number(concepto.precio) - Number(concepto.coste_directo)),
                    )}
                  </td>
                  <td />
                </tr>
              )}
              <tr className="fila-total">
                <td colSpan={5} className="table__num total-label">
                  Precio por {concepto.unidad}
                </td>
                <td className="table__num">
                  <strong>{formatoImporte(concepto.precio)}</strong>
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        )}
      </div>

      {anadiendoLinea && (
        <AnadirLineaModal
          conceptoId={id}
          excluir={concepto.id}
          onClose={() => setAnadiendoLinea(false)}
          onAnadida={() => {
            setAnadiendoLinea(false)
            void cargar()
          }}
        />
      )}
    </>
  )

  const pestanaTarifas = (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          Precio de suministro: proveedor + fecha. Se guarda con cuatro decimales porque las
          tarifas llegan así; el redondeo a dos se aplica al encadenar conceptos.
        </p>
        <button className="btn" onClick={() => setNuevaTarifa(true)}>
          <Plus size={16} aria-hidden="true" />
          Añadir tarifa
        </button>
      </div>

      <div className="table-wrap">
        {concepto.suministros.length === 0 ? (
          <EmptyState title="Sin tarifas">
            Añade el precio de al menos un proveedor para que este concepto pueda tomar su
            precio de una tarifa.
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
              {concepto.suministros.map((s) => (
                <FilaTarifa key={s.id} tarifa={s} onCambio={cargar} />
              ))}
            </tbody>
          </table>
        )}
      </div>

      {nuevaTarifa && (
        <NuevaTarifaModal
          conceptoId={id}
          onClose={() => setNuevaTarifa(false)}
          onCreada={() => {
            setNuevaTarifa(false)
            void cargar()
          }}
        />
      )}
    </>
  )

  const pestanaUso = (
    <>
      <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Dónde participa</h2>
      <p className="page-lead">
        Otros conceptos que lo contienen (directa o indirectamente) y partidas de presupuestos
        que lo usan.
      </p>

      <div className="table-wrap">
        {enDescomposiciones.length === 0 ? (
          <EmptyState title="No entra en ningún descompuesto todavía" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Descripción</th>
                <th>Nivel</th>
                <th className="table__num">Rendimiento efectivo</th>
                <th className="table__num">Su precio</th>
              </tr>
            </thead>
            <tbody>
              {enDescomposiciones.map((uso) => (
                <tr key={uso.id}>
                  <td className="table__code">{uso.codigo}</td>
                  <td>
                    <Link className="table__link" to={`/banco-precios/${uso.id}`}>
                      {uso.resumen}
                    </Link>
                  </td>
                  <td>
                    <span className={`chip chip--${uso.tipo}`}>
                      {ETIQUETA_TIPO_CONCEPTO[uso.tipo]}
                    </span>
                  </td>
                  <td className="table__num">{formatoImporte(uso.rendimiento, 3)}</td>
                  <td className="table__num">{formatoImporte(uso.precio)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="table-wrap" style={{ marginTop: 'var(--sp-4)' }}>
        {enPartidas.length === 0 ? (
          <EmptyState title="No aparece en ninguna partida presupuestada todavía" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Presupuesto</th>
                <th>Código</th>
                <th>Descripción</th>
                <th className="table__num">Medición</th>
                <th className="table__num">Precio</th>
                <th className="table__num">Importe</th>
              </tr>
            </thead>
            <tbody>
              {enPartidas.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link className="table__link" to={`/presupuestos/${p.presupuesto_id}`}>
                      {p.presupuesto_nombre}
                    </Link>
                  </td>
                  <td className="table__code">{p.codigo}</td>
                  <td>{p.resumen}</td>
                  <td className="table__num">{formatoImporte(p.medicion, 3)}</td>
                  <td className="table__num">{formatoImporte(p.precio)}</td>
                  <td className="table__num">
                    <strong>{formatoImporte(p.importe)}</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {ventasDisponibles && (
        <>
          <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, marginTop: 'var(--sp-6)' }}>
            Qué venta ha tenido
          </h2>
          <p className="page-lead">
            Presupuestado cuenta toda partida que lo referencia, esté o no certificada todavía;
            facturado solo lo que una certificación ya emitida ha reconocido como ejecutado.
          </p>
          <div className="ficha-datos">
            <div>
              <div className="barra-acciones__etiqueta">Presupuestado</div>
              <div className="ficha-datos__valor">
                {ventas ? formatoImporte(ventas.presupuestado_importe) : '—'} €
              </div>
              <div className="muted">{ventas?.presupuestado_partidas ?? 0} partidas</div>
            </div>
            <div>
              <div className="barra-acciones__etiqueta">Facturado</div>
              <div className="ficha-datos__valor">
                {ventas ? formatoImporte(ventas.facturado_importe) : '—'} €
              </div>
              <div className="muted">{ventas?.facturado_lineas ?? 0} líneas certificadas</div>
            </div>
          </div>
        </>
      )}
    </>
  )

  const pestanaHistorico = (
    <>
      <p className="page-lead" style={{ marginTop: 0 }}>
        Cada fila es un precio que este concepto ha llegado a tener.
      </p>

      <div className="table-wrap">
        {historico.length === 0 ? (
          <EmptyState title="Sin histórico todavía" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th className="table__num">Precio</th>
                <th>Origen</th>
              </tr>
            </thead>
            <tbody>
              {historico.map((h) => (
                <tr key={h.id}>
                  <td>{formatoFecha(h.fecha)}</td>
                  <td className="table__num">{formatoImporte(h.precio)}</td>
                  <td>{ETIQUETA_ORIGEN_PRECIO[h.origen_precio]}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )

  const pestanas: PestanaFicha[] = [
    { id: 'ficha', etiqueta: 'Ficha', icono: 'datos', contenido: pestanaFicha },
    { id: 'descompuesto', etiqueta: 'Descompuesto', icono: 'layers', contenido: pestanaDescompuesto },
    { id: 'tarifas', etiqueta: 'Tarifas', icono: 'truck', contenido: pestanaTarifas },
    { id: 'uso', etiqueta: 'Dónde participa', icono: 'buscar', contenido: pestanaUso },
    { id: 'historico', etiqueta: 'Histórico', icono: 'recalcular', contenido: pestanaHistorico },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.conceptos.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {concepto.resumen} <span className="table__code">{concepto.codigo}</span>
        </>
      }
      subtitulo={
        <div className="page-head" style={{ marginBottom: 0 }}>
          <p className="page-lead" style={{ marginBottom: 0 }}>
            <span className={`chip chip--${concepto.tipo}`}>
              {ETIQUETA_TIPO_CONCEPTO[concepto.tipo]}
            </span>{' '}
            {ETIQUETA_NATURALEZA[concepto.naturaleza]}
            {concepto.clase && <> · unitario {concepto.clase}</>} · precio{' '}
            {ETIQUETA_ORIGEN_PRECIO[concepto.origen_precio].toLowerCase()}
          </p>
          <div className="precio-cabecera">
            <div className="precio-cabecera__valor">{formatoImporte(concepto.precio)} €</div>
            <div className="precio-cabecera__unidad">por {concepto.unidad}</div>
          </div>
        </div>
      }
      acciones={
        <Tooltip texto="Eliminar esta ficha del banco de precios">
          <button className="btn btn--danger" onClick={() => void eliminar()}>
            <Trash2 size={16} aria-hidden="true" />
            Eliminar
          </button>
        </Tooltip>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}

function FilaLinea({ linea, onCambio }: { linea: Linea; onCambio: () => void }) {
  const [rendimiento, setRendimiento] = useState(linea.rendimiento)
  const [error, setError] = useState<string | null>(null)

  // El rendimiento se guarda al salir del campo, no en cada tecla: cada
  // guardado dispara un recálculo en cascada.
  async function guardarRendimiento() {
    if (rendimiento === linea.rendimiento) return
    try {
      await api.descomposicion.update(linea.id, { rendimiento })
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setRendimiento(linea.rendimiento)
    }
  }

  async function eliminar() {
    await api.descomposicion.remove(linea.id)
    onCambio()
  }

  return (
    <tr>
      <td className="table__code">{linea.hijo_codigo}</td>
      <td>
        <Link className="table__link" to={`/banco-precios/${linea.hijo_id}`}>
          {linea.hijo_resumen}
        </Link>
        {error && <div className="muted">{error}</div>}
      </td>
      <td className="table__code">{linea.hijo_unidad}</td>
      <td className="table__num">
        <input
          className="input input--celda"
          type="number"
          step="0.000001"
          value={rendimiento}
          onChange={(e) => setRendimiento(e.target.value)}
          onBlur={() => void guardarRendimiento()}
        />
      </td>
      <td className="table__num">{formatoImporte(linea.hijo_precio)}</td>
      <td className="table__num">
        <strong>{formatoImporte(linea.importe)}</strong>
      </td>
      <td className="table__actions">
        <button className="btn btn--sm btn--danger" onClick={() => void eliminar()}>
          <Trash2 size={14} aria-hidden="true" />
          Quitar
        </button>
      </td>
    </tr>
  )
}

function AnadirLineaModal({
  conceptoId,
  excluir,
  onClose,
  onAnadida,
}: {
  conceptoId: string
  excluir: string
  onClose: () => void
  onAnadida: () => void
}) {
  const [q, setQ] = useState('')
  const [candidatos, setCandidatos] = useState<Concepto[]>([])
  const [hijoId, setHijoId] = useState('')
  const [rendimiento, setRendimiento] = useState('1')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const id = setTimeout(() => {
      void api.conceptos
        .list({ q: q || undefined, activo: true, limit: 50 })
        .then((page) => setCandidatos(page.items.filter((c) => c.id !== excluir)))
        .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
    }, 250)
    return () => clearTimeout(id)
  }, [q, excluir])

  async function guardar() {
    setError(null)
    try {
      await api.conceptos.addLinea(conceptoId, { hijo_id: hijoId, rendimiento })
      onAnadida()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Añadir al descompuesto" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Buscar en el banco de precios">
          <input
            className="input"
            placeholder="Código o descripción…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            autoFocus
          />
        </Field>

        <div className="lista-seleccion">
          {candidatos.length === 0 ? (
            <div className="muted" style={{ padding: 'var(--sp-3)' }}>
              Sin resultados
            </div>
          ) : (
            candidatos.map((c) => (
              <button
                key={c.id}
                className={
                  hijoId === c.id ? 'lista-seleccion__item is-activo' : 'lista-seleccion__item'
                }
                onClick={() => setHijoId(c.id)}
              >
                <span className="table__code">{c.codigo}</span>
                <span className="lista-seleccion__texto">{c.resumen}</span>
                <span className={`chip chip--${c.tipo}`}>{ETIQUETA_TIPO_CONCEPTO[c.tipo]}</span>
                <span className="table__num">
                  {formatoImporte(c.precio)} €/{c.unidad}
                </span>
              </button>
            ))
          )}
        </div>

        <div style={{ marginTop: 'var(--sp-4)', maxWidth: 220 }}>
          <Field label="Rendimiento" hint="Cantidad por unidad del padre">
            <input
              className="input"
              type="number"
              step="0.000001"
              value={rendimiento}
              onChange={(e) => setRendimiento(e.target.value)}
            />
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={hijoId === '' || rendimiento === ''}
          onClick={() => void guardar()}
        >
          <Plus size={16} aria-hidden="true" />
          Añadir
        </button>
      </div>
    </Modal>
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
            <Star size={14} aria-hidden="true" />
            Preferente
          </button>
        )}{' '}
        <button className="btn btn--sm btn--danger" onClick={() => void eliminar()}>
          <Trash2 size={14} aria-hidden="true" />
          Eliminar
        </button>
      </td>
    </tr>
  )
}

function NuevaTarifaModal({
  conceptoId,
  onClose,
  onCreada,
}: {
  conceptoId: string
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
      await api.conceptos.addSuministro(conceptoId, {
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
              <Field ancho="doble" label="Referencia del proveedor">
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
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={proveedorId === '' || precio === ''}
          onClick={() => void guardar()}
        >
          <Plus size={16} aria-hidden="true" />
          Crear
        </button>
      </div>
    </Modal>
  )
}
