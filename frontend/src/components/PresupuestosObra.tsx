/** Los presupuestos que se están ejecutando en una obra.
 *
 *  Una obra real no ejecuta un único presupuesto: se firma un contrato y
 *  después van entrando adendas, imprevistos y ampliaciones. El primero es el
 *  «principal» — el que originó la obra y contra el que se compara el coste —
 *  y los demás entran como anexos, marcados como tal para que en el árbol de
 *  obra se distinga lo contratado al arrancar de lo que vino después.
 *
 *  El principal no se puede quitar: es la referencia de la comparación de
 *  costes. El backend también lo impide, esto solo evita el viaje.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { FilePlus2, Plus, Trash2, X } from 'lucide-react'

import { api } from '../lib/api'
import type { PresupuestoResumen, VinculoPresupuesto } from '../lib/api'
import { EmptyState, ErrorNotice, Field, Modal, Tooltip, formatoImporte } from './ui'

export function PresupuestosObra({
  obraId,
  onCambio,
}: {
  obraId: string
  /** La obra enseña el PEM del principal en su cabecera: si cambia, recarga. */
  onCambio?: () => void
}) {
  const [vinculos, setVinculos] = useState<VinculoPresupuesto[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [anadiendo, setAnadiendo] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setVinculos(await api.obras.presupuestos(obraId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [obraId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function quitar(vinculo: VinculoPresupuesto) {
    if (
      !window.confirm(
        `¿Quitar «${vinculo.presupuesto_nombre}» de esta obra? El presupuesto no se borra, ` +
          'solo deja de estar en ejecución aquí.',
      )
    ) {
      return
    }
    try {
      await api.obras.desvincularPresupuesto(obraId, vinculo.id)
      await cargar()
      onCambio?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <>
      <div className="page-head" style={{ marginTop: 'var(--sp-6)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Presupuestos en ejecución</h2>
        <Tooltip texto="Poner otro presupuesto en ejecución en esta obra, como anexo">
          <button className="btn" onClick={() => setAnadiendo(true)}>
            <Plus size={16} aria-hidden="true" />
            Añadir anexo
          </button>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      <div className="table-wrap">
        {vinculos !== null && vinculos.length === 0 ? (
          <EmptyState title="Sin presupuestos">
            Esta obra no tiene ningún presupuesto en ejecución.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Presupuesto</th>
                <th>Procedencia</th>
                <th>Desde</th>
                <th>Notas</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {(vinculos ?? []).map((v) => (
                <tr key={v.id}>
                  <td>
                    <Link to={`/presupuestos/${v.presupuesto_id}`}>{v.presupuesto_codigo}</Link>{' '}
                    {v.presupuesto_nombre}
                  </td>
                  <td>
                    <span className={`chip chip--vinculo-${v.tipo}`}>
                      {v.tipo === 'principal' ? 'Contrato principal' : 'Anexo / adenda'}
                    </span>
                  </td>
                  <td>{v.fecha_vinculacion}</td>
                  <td>{v.notas ?? <span className="muted">—</span>}</td>
                  <td className="table__actions">
                    {v.tipo === 'principal' ? (
                      <Tooltip texto="El principal es la referencia del coste: no se puede quitar">
                        <span className="muted">—</span>
                      </Tooltip>
                    ) : (
                      <button className="btn btn--sm" onClick={() => void quitar(v)}>
                        <Trash2 size={14} aria-hidden="true" />
                        Quitar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {anadiendo && (
        <AnadirAnexoModal
          obraId={obraId}
          yaVinculados={(vinculos ?? []).map((v) => v.presupuesto_id)}
          onClose={() => setAnadiendo(false)}
          onAnadido={() => {
            setAnadiendo(false)
            void cargar()
            onCambio?.()
          }}
        />
      )}
    </>
  )
}

function AnadirAnexoModal({
  obraId,
  yaVinculados,
  onClose,
  onAnadido,
}: {
  obraId: string
  yaVinculados: string[]
  onClose: () => void
  onAnadido: () => void
}) {
  const [candidatos, setCandidatos] = useState<PresupuestoResumen[] | null>(null)
  const [presupuestoId, setPresupuestoId] = useState('')
  const [notas, setNotas] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    let vigente = true
    api.presupuestos
      // Las plantillas no se ejecutan, y de las versiones solo interesa la
      // última: un anexo se firma sobre la vigente, no sobre un borrador viejo.
      .list({ es_plantilla: false, solo_ultima_version: true, limit: 200 })
      .then((pagina) => {
        if (!vigente) return
        setCandidatos(pagina.items.filter((p) => !yaVinculados.includes(p.id)))
      })
      .catch((err: unknown) => {
        if (vigente) {
          setError(err instanceof Error ? err.message : 'No se han podido cargar los presupuestos')
        }
      })
    return () => {
      vigente = false
    }
    // La dependencia es el contenido, no el array: el padre construye uno
    // nuevo en cada render y comparar por identidad relanzaría la carga en
    // bucle.
  }, [yaVinculados.join(',')])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.obras.vincularPresupuesto(obraId, {
        presupuesto_id: presupuestoId,
        tipo: 'anexo',
        notas: notas.trim() || null,
      })
      onAnadido()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title="Añadir anexo a la obra" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="aceptar__intro">
          El presupuesto quedará aprobado y con los precios congelados, y en la obra se marcará
          como anexo.
        </p>
        <Field label="Presupuesto" hint="Solo los que no están ya en esta obra">
          <select
            className="select"
            value={presupuestoId}
            onChange={(e) => setPresupuestoId(e.target.value)}
            autoFocus
          >
            <option value="">Elige un presupuesto…</option>
            {(candidatos ?? []).map((p) => (
              <option key={p.id} value={p.id}>
                {p.codigo} · {p.nombre} · {formatoImporte(p.total)}
              </option>
            ))}
          </select>
        </Field>
        {candidatos !== null && candidatos.length === 0 && (
          <p className="muted">No queda ningún presupuesto por vincular.</p>
        )}
        <Field label="Notas" hint="Por qué se contrata: un imprevisto, una ampliación…">
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
          disabled={!presupuestoId || guardando}
          onClick={() => void guardar()}
        >
          {!guardando && <FilePlus2 size={16} aria-hidden="true" />}
          {guardando ? 'Añadiendo…' : 'Añadir como anexo'}
        </button>
      </div>
    </Modal>
  )
}
