import { useEffect, useState } from 'react'
import { Check, Plus, Trash2 } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { FormulaMedicion } from '../lib/api'
import { useToast } from '../toast'

/** Catálogo de fórmulas de medición (Fase 37).
 *
 *  Vive a nivel de cuenta, como el diccionario: se comparte entre las
 *  organizaciones de la misma cuenta. Se puede crear una fórmula sin salir de
 *  aquí, y antes de guardarla se prueba con valores para ver qué da — la
 *  expresión la valida el servidor con un analizador seguro, nunca `eval`. */
export function FormulasModal({
  onClose,
  onCambio,
}: {
  onClose: () => void
  onCambio: () => void
}) {
  const { notificar } = useToast()
  const [formulas, setFormulas] = useState<FormulaMedicion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [nombre, setNombre] = useState('')
  const [expresion, setExpresion] = useState('')
  const [prueba, setPrueba] = useState<{ variables: string[]; resultado: string } | null>(null)
  const [valores, setValores] = useState<Record<string, string>>({})
  const [guardando, setGuardando] = useState(false)

  async function cargar() {
    try {
      setFormulas(await api.formulasMedicion.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  useEffect(() => {
    void cargar()
  }, [])

  // Al escribir la expresión se pregunta al servidor qué variables tiene y
  // cuánto da con los valores actuales. Con un respiro, para no consultar por
  // cada tecla.
  useEffect(() => {
    if (expresion.trim() === '') {
      setPrueba(null)
      return
    }
    let cancelado = false
    const temporizador = setTimeout(() => {
      void api.formulasMedicion
        .probar(expresion, valores)
        .then((r) => {
          if (!cancelado) {
            setPrueba(r)
            setError(null)
          }
        })
        .catch((err) => {
          if (!cancelado) {
            setPrueba(null)
            setError(err instanceof Error ? err.message : 'Error desconocido')
          }
        })
    }, 400)
    return () => {
      cancelado = true
      clearTimeout(temporizador)
    }
  }, [expresion, valores])

  async function crear() {
    setGuardando(true)
    setError(null)
    try {
      await api.formulasMedicion.create({ nombre, expresion })
      setNombre('')
      setExpresion('')
      setValores({})
      setPrueba(null)
      await cargar()
      onCambio()
      notificar('Fórmula creada')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar(formula: FormulaMedicion) {
    if (
      !window.confirm(
        `¿Eliminar la fórmula «${formula.nombre}»? Las mediciones ya hechas con ella no cambian.`,
      )
    ) {
      return
    }
    try {
      await api.formulasMedicion.remove(formula.id)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Fórmulas de medición" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />

        <div className="form-section__title">Nueva fórmula</div>
        <p className="form-section__note">
          Escribe la expresión con los nombres que quieras para las variables, por ejemplo{' '}
          <code>base * altura / 2</code>. Puedes usar <code>+ - * / ** %</code>, paréntesis,{' '}
          <code>pi</code> y las funciones <code>sqrt, sin, cos, tan, radians, abs, min, max, round</code>.
        </p>
        <div className="form-grid">
          <Field label="Nombre">
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Field>
          <Field ancho="doble" label="Expresión">
            <input
              className="input"
              value={expresion}
              onChange={(e) => setExpresion(e.target.value)}
              placeholder="base * altura / 2"
            />
          </Field>
        </div>

        {prueba && (
          <div style={{ marginTop: 'var(--sp-3)' }}>
            <div className="field__label">Probar con valores</div>
            {prueba.variables.length === 0 ? (
              <p className="muted">Esta fórmula no tiene variables: da siempre el mismo valor.</p>
            ) : (
              <div className="form-grid">
                {prueba.variables.map((v) => (
                  <Field key={v} label={v}>
                    <input
                      className="input"
                      type="number"
                      step="any"
                      value={valores[v] ?? ''}
                      onChange={(e) => setValores((prev) => ({ ...prev, [v]: e.target.value }))}
                    />
                  </Field>
                ))}
              </div>
            )}
            <div className="resumen-totales" style={{ marginTop: 'var(--sp-2)' }}>
              <div className="resumen-totales__fila is-total">
                <span>Resultado</span>
                <span className="resumen-totales__valor">
                  {formatoImporte(prueba.resultado, 3)}
                </span>
              </div>
            </div>
          </div>
        )}

        <div className="form-actions" style={{ justifyContent: 'flex-start' }}>
          <button
            className="btn btn--primary"
            disabled={guardando || nombre.trim() === '' || !prueba}
            onClick={() => void crear()}
          >
            <Plus size={16} aria-hidden="true" />
            {guardando ? 'Creando…' : 'Crear fórmula'}
          </button>
        </div>
      </div>

      <div className="form-section">
        <div className="form-section__title">Catálogo</div>
        {formulas.length === 0 ? (
          <EmptyState title="Sin fórmulas" />
        ) : (
          <div className="table-wrap" style={{ maxHeight: 300 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th>Expresión</th>
                  <th>Variables</th>
                  <th className="table__actions" />
                </tr>
              </thead>
              <tbody>
                {formulas.map((f) => (
                  <tr key={f.id}>
                    <td>{f.nombre}</td>
                    <td>
                      <code>{f.expresion}</code>
                    </td>
                    <td className="muted">{f.variables.join(', ') || '—'}</td>
                    <td className="table__actions">
                      <Tooltip texto="Eliminar esta fórmula">
                        <button
                          className="btn btn--sm btn--danger btn--solo-icono"
                          aria-label={`Eliminar ${f.nombre}`}
                          onClick={() => void eliminar(f)}
                        >
                          <Trash2 size={14} aria-hidden="true" />
                        </button>
                      </Tooltip>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="form-actions">
        <button className="btn btn--primary" onClick={onClose}>
          <Check size={16} aria-hidden="true" />
          Hecho
        </button>
      </div>
    </Modal>
  )
}
