import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Checkbox, EmptyState, ErrorNotice, Field, Modal, ModalPantalla, formatoImporte } from '../components/ui'
import {
  ETIQUETA_NATURALEZA,
  ETIQUETA_ORIGEN_PRECIO,
  ETIQUETA_TIPO_CONCEPTO,
  api,
} from '../lib/api'
import type { Concepto, ConceptoDetalle as Detalle, Linea, Uso } from '../lib/api'
import { useContextoPrecios } from './Precios'

export function PrecioDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoPrecios()
  const [concepto, setConcepto] = useState<Detalle | null>(null)
  const [usos, setUsos] = useState<Uso[]>([])
  const [borrador, setBorrador] = useState<Partial<Detalle>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [anadiendo, setAnadiendo] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const [datos, quienLoUsa] = await Promise.all([
        api.conceptos.get(id),
        api.conceptos.dondeSeUsa(id),
      ])
      setConcepto(datos)
      setUsos(quienLoUsa)
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
    navigate('/precios')
  }

  if (error && !concepto) {
    return (
      <ModalPantalla title="Concepto" onClose={cerrar}>
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

  return (
    <ModalPantalla
      title={
        <>
          {concepto.resumen} <span className="table__code">{concepto.codigo}</span>
        </>
      }
      onClose={cerrar}
    >
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          <span className={`chip chip--${concepto.tipo}`}>
            {ETIQUETA_TIPO_CONCEPTO[concepto.tipo]}
          </span>
          {concepto.clase && <> · unitario {concepto.clase}</>} · precio{' '}
          {ETIQUETA_ORIGEN_PRECIO[concepto.origen_precio].toLowerCase()}
        </p>
        <div className="precio-cabecera">
          <div className="precio-cabecera__valor">{formatoImporte(concepto.precio)} €</div>
          <div className="precio-cabecera__unidad">por {concepto.unidad}</div>
        </div>
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
            <Field label="Unidad">
              <input
                className="input"
                value={valor('unidad')}
                onChange={(e) => cambiar('unidad', e.target.value)}
              />
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
              label="Precio"
              hint={
                calculado
                  ? 'Lo fija el descompuesto'
                  : concepto.origen_precio === 'producto'
                    ? 'Lo fija la tarifa del catálogo'
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
            <Field label="Descripción larga">
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
          <button className="btn btn--danger" onClick={() => void eliminar()}>
            Eliminar
          </button>
          <span style={{ flex: 1 }} />
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

      <div className="page-head" style={{ marginTop: 'var(--sp-6)' }}>
        <div>
          <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Descompuesto</h2>
          <p className="page-lead">
            Cada importe se redondea a dos decimales antes de sumar, como en Presto: así el
            descompuesto impreso cuadra columna a columna.
          </p>
        </div>
        <button className="btn" onClick={() => setAnadiendo(true)}>
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

      <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, marginTop: 'var(--sp-6)' }}>
        Dónde se usa
      </h2>
      <p className="page-lead">
        Conceptos que contienen a este. Un cambio de precio aquí les llega en cascada.
      </p>

      <div className="table-wrap">
        {usos.length === 0 ? (
          <EmptyState title="No lo usa nadie todavía" />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Descripción</th>
                <th>Nivel</th>
                <th className="table__num">Lleva</th>
                <th className="table__num">Su precio</th>
              </tr>
            </thead>
            <tbody>
              {usos.map((uso) => (
                <tr key={uso.id}>
                  <td className="table__code">{uso.codigo}</td>
                  <td>
                    <Link className="table__link" to={`/precios/${uso.id}`}>
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

      {anadiendo && (
        <AnadirLineaModal
          conceptoId={id}
          excluir={concepto.id}
          onClose={() => setAnadiendo(false)}
          onAnadida={() => {
            setAnadiendo(false)
            void cargar()
          }}
        />
      )}
    </ModalPantalla>
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
        <Link className="table__link" to={`/precios/${linea.hijo_id}`}>
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
        <Field label="Buscar concepto">
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
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={hijoId === '' || rendimiento === ''}
          onClick={() => void guardar()}
        >
          Añadir
        </button>
      </div>
    </Modal>
  )
}
