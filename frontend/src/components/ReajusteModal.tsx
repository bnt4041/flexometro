import { useState } from 'react'
import { Lock, RefreshCw, Save, X } from 'lucide-react'

import { ErrorNotice, Field, Modal, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { Reajuste, TipoReajuste } from '../lib/api'
import { useToast } from '../toast'

/** Reajuste del presupuesto a un importe o a un margen objetivo (Fase 36).
 *
 *  Nunca aplica a ciegas: primero se simula y se enseña partida a partida qué
 *  va a cambiar, y solo después se confirma. Las partidas con la venta
 *  bloqueada no se tocan, así que el resto absorbe toda la diferencia. */
export function ReajusteModal({
  presupuestoId,
  totalActual,
  onClose,
  onAplicado,
}: {
  presupuestoId: string
  totalActual: string
  onClose: () => void
  onAplicado: () => void
}) {
  const { notificar } = useToast()
  const [tipo, setTipo] = useState<TipoReajuste>('importe')
  const [valor, setValor] = useState(totalActual)
  const [vista, setVista] = useState<Reajuste | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  async function lanzar(aplicar: boolean) {
    setOcupado(true)
    setError(null)
    try {
      const r = await api.presupuestos.reajustar(presupuestoId, {
        tipo,
        valor: valor.replace(',', '.'),
        aplicar,
      })
      if (aplicar) {
        notificar(
          r.partidas_afectadas === 1
            ? '1 partida reajustada'
            : `${r.partidas_afectadas} partidas reajustadas`,
        )
        onAplicado()
      } else {
        setVista(r)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setVista(null)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <Modal title="Reajustar el presupuesto" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          Las partidas con la venta bloqueada (candado) no se tocan: el resto absorbe la
          diferencia, repartida en proporción a lo que vale cada una.
        </p>
        <div className="form-grid">
          <Field label="Objetivo">
            <select
              className="select"
              value={tipo}
              onChange={(e) => {
                setTipo(e.target.value as TipoReajuste)
                setVista(null)
              }}
            >
              <option value="importe">Importe total (sin IVA)</option>
              <option value="margen">Margen sobre la venta (%)</option>
            </select>
          </Field>
          <Field
            label={tipo === 'importe' ? 'Importe objetivo (€)' : 'Margen objetivo (%)'}
            hint={tipo === 'margen' ? 'El beneficio como porcentaje de la venta' : undefined}
          >
            <input
              className="input"
              type="number"
              step="0.01"
              value={valor}
              onChange={(e) => {
                setValor(e.target.value)
                setVista(null)
              }}
              autoFocus
            />
          </Field>
        </div>
        <div className="form-actions" style={{ justifyContent: 'flex-start' }}>
          <button
            className="btn"
            disabled={ocupado || valor.trim() === ''}
            onClick={() => void lanzar(false)}
          >
            <RefreshCw size={16} aria-hidden="true" />
            {ocupado && !vista ? 'Calculando…' : 'Ver el efecto'}
          </button>
        </div>

        {vista && (
          <>
            <div className="resumen-totales" style={{ marginTop: 'var(--sp-4)' }}>
              <div className="resumen-totales__fila">
                <span>Coste</span>
                <span className="resumen-totales__valor">{formatoImporte(vista.coste)} €</span>
              </div>
              <div className="resumen-totales__fila is-suave">
                <span>Venta actual (margen {formatoImporte(vista.margen_antes)} %)</span>
                <span className="resumen-totales__valor">
                  {formatoImporte(vista.venta_antes)} €
                </span>
              </div>
              <div className="resumen-totales__fila is-total">
                <span>Venta tras reajustar (margen {formatoImporte(vista.margen_despues)} %)</span>
                <span className="resumen-totales__valor">
                  {formatoImporte(vista.venta_despues)} €
                </span>
              </div>
              {Number(vista.diferencia) !== 0 && (
                <div className="resumen-totales__fila is-suave">
                  <span>
                    Se queda a {formatoImporte(vista.diferencia)} € del objetivo (
                    {formatoImporte(vista.objetivo_venta)} €) por el redondeo de los precios
                    unitarios
                  </span>
                  <span />
                </div>
              )}
            </div>

            {vista.partidas_bajo_coste > 0 && (
              <div className="notice notice--aviso" style={{ marginTop: 'var(--sp-3)' }}>
                Con este objetivo, <strong>{vista.partidas_bajo_coste}</strong>{' '}
                {vista.partidas_bajo_coste === 1 ? 'partida quedaría' : 'partidas quedarían'} por
                debajo de su coste.
              </div>
            )}

            <div className="table-wrap" style={{ marginTop: 'var(--sp-3)', maxHeight: 260 }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Partida</th>
                    <th className="table__num">Coste</th>
                    <th className="table__num">Venta antes</th>
                    <th className="table__num">Venta después</th>
                  </tr>
                </thead>
                <tbody>
                  {vista.lineas.map((l) => (
                    <tr key={l.partida_id}>
                      <td>
                        {l.bloqueada && (
                          <>
                            <Lock size={12} aria-hidden="true" />{' '}
                          </>
                        )}
                        <span className="table__code">{l.codigo}</span> {l.resumen}
                      </td>
                      <td className="table__num">{formatoImporte(l.coste)}</td>
                      <td className="table__num muted">{formatoImporte(l.venta_antes)}</td>
                      <td
                        className="table__num"
                        style={
                          Number(l.venta_despues) < Number(l.coste)
                            ? { color: 'var(--c-danger)', fontWeight: 600 }
                            : undefined
                        }
                      >
                        <strong>{formatoImporte(l.venta_despues)}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
          disabled={!vista || ocupado}
          onClick={() => void lanzar(true)}
        >
          <Save size={16} aria-hidden="true" />
          Aplicar el reajuste
        </button>
      </div>
    </Modal>
  )
}
