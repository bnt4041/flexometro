import { useCallback, useEffect, useState } from 'react'

import { Checkbox, ErrorNotice, Field } from './ui'
import { api } from '../lib/api'
import type { CampoLibreDefinicion, EntidadCampoLibre } from '../lib/api'
import { useToast } from '../toast'

/** Sección de campos libres (Fase 21-22) de un registro concreto — se pinta
 *  sola si la cuenta tiene definido al menos un campo activo para esta
 *  `entidad` (ver Ajustes > Campos libres); si no hay ninguno, no renderiza
 *  nada, para no dejar una sección vacía en cada ficha. */
export function CamposLibres({ entidad, entidadId }: { entidad: EntidadCampoLibre; entidadId: string }) {
  const { notificar } = useToast()
  const [definiciones, setDefiniciones] = useState<CampoLibreDefinicion[]>([])
  const [valores, setValores] = useState<Record<string, string | null>>({})
  const [borrador, setBorrador] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const [defs, vals] = await Promise.all([
        api.camposLibres.definiciones(entidad),
        api.camposLibres.valores(entidad, entidadId),
      ])
      setDefiniciones(defs)
      setValores(vals)
      setBorrador({})
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entidad, entidadId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  if (definiciones.length === 0) return null

  const valor = (clave: string) => borrador[clave] ?? valores[clave] ?? ''
  const cambiar = (clave: string, v: string | null) => setBorrador((b) => ({ ...b, [clave]: v }))
  const hayCambios = Object.keys(borrador).length > 0

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const actualizados = await api.camposLibres.establecerValores(entidad, entidadId, borrador)
      setValores(actualizados)
      setBorrador({})
      notificar('Campos guardados')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="card">
      <div className="form-section">
        <div className="form-section__title">Campos libres</div>
        <ErrorNotice error={error} />
        <div className="form-grid">
          {definiciones.map((d) => (
            <Field key={d.clave} label={d.etiqueta}>
              {d.tipo === 'booleano' ? (
                <Checkbox
                  label=""
                  checked={valor(d.clave) === 'true'}
                  onChange={(v) => cambiar(d.clave, v ? 'true' : 'false')}
                />
              ) : d.tipo === 'select' ? (
                <select
                  className="select"
                  value={valor(d.clave)}
                  onChange={(e) => cambiar(d.clave, e.target.value || null)}
                >
                  <option value="">Sin definir</option>
                  {d.opciones.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="input"
                  type={d.tipo === 'numero' ? 'number' : d.tipo === 'fecha' ? 'date' : 'text'}
                  value={valor(d.clave)}
                  onChange={(e) => cambiar(d.clave, e.target.value || null)}
                />
              )}
            </Field>
          ))}
        </div>
        <div className="form-actions">
          <button
            className="btn btn--primary"
            disabled={!hayCambios || guardando}
            onClick={() => void guardar()}
          >
            {guardando ? 'Guardando…' : 'Guardar campos libres'}
          </button>
        </div>
      </div>
    </div>
  )
}
