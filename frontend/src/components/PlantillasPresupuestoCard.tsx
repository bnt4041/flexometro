import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Trash2, Upload } from 'lucide-react'

import { ErrorNotice, Field } from './ui'
import { api, descargar } from '../lib/api'
import type { PlantillaPresupuesto } from '../lib/api'
import { useToast } from '../toast'

/** Plantillas Word para exportar presupuestos con diseño propio (Fase 39):
 *  las de sistema vienen ya creadas y sirven de patrón de partida —
 *  descárgalas, edítalas en Word manteniendo las claves entre llaves dobles,
 *  y sube el resultado como una plantilla propia. Se embebe en los ajustes
 *  propios del módulo de Presupuestos, igual que `NumeracionCard`. */
export function PlantillasPresupuestoCard() {
  const { notificar } = useToast()
  const [plantillas, setPlantillas] = useState<PlantillaPresupuesto[]>([])
  const [nombre, setNombre] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [subiendo, setSubiendo] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const cargar = useCallback(async () => {
    try {
      setPlantillas(await api.ajustes.plantillasPresupuesto.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function subir(archivo: File | null) {
    if (!archivo) return
    if (!nombre.trim()) {
      setError('Ponle un nombre a la plantilla antes de subirla')
      return
    }
    setSubiendo(true)
    setError(null)
    try {
      const plantilla = await api.ajustes.plantillasPresupuesto.subir(nombre.trim(), archivo)
      setPlantillas((actual) => [...actual, plantilla])
      setNombre('')
      notificar(
        plantilla.claves_detectadas.length > 0
          ? `Plantilla subida. Claves reconocidas: ${plantilla.claves_detectadas.join(', ')}`
          : 'Plantilla subida, pero no se ha reconocido ninguna clave — revisa que uses {{ }} dentro del Word',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setSubiendo(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function eliminar(plantilla: PlantillaPresupuesto) {
    if (!window.confirm(`¿Eliminar la plantilla «${plantilla.nombre}»?`)) return
    try {
      await api.ajustes.plantillasPresupuesto.eliminar(plantilla.id)
      setPlantillas((actual) => actual.filter((p) => p.id !== plantilla.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-5)' }}>
      <h2 style={{ fontSize: 'var(--fs-lg)', fontWeight: 650, margin: '0 0 var(--sp-1)' }}>
        Plantillas de presupuesto
      </h2>
      <p className="form-section__note">
        Diseña en Word cómo quieres que se vea el presupuesto al exportarlo. Descarga una
        plantilla de sistema como punto de partida, edítala manteniendo las claves entre llaves
        dobles (<code>presupuesto.codigo</code>, <code>cliente.razon_social</code>, la tabla de{' '}
        <code>partidas</code>…) y súbela aquí. Desde cada presupuesto podrás descargarla ya
        rellena, en PDF o en Word.
      </p>

      <ErrorNotice error={error} />

      <div className="toolbar">
        <Field label="Nombre de la plantilla nueva">
          <input
            className="input"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Oferta para cliente"
          />
        </Field>
        <button className="btn btn--primary" disabled={subiendo} onClick={() => inputRef.current?.click()}>
          <Upload size={16} aria-hidden="true" />
          {subiendo ? 'Subiendo…' : 'Subir .docx'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".docx"
          style={{ display: 'none' }}
          onChange={(e) => void subir(e.target.files?.[0] ?? null)}
        />
      </div>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Claves reconocidas</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {plantillas.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.nombre}
                  {p.es_sistema && <span className="badge badge--info" style={{ marginLeft: 'var(--sp-2)' }}>Sistema</span>}
                </td>
                <td className="muted">{p.claves_detectadas.join(', ') || '—'}</td>
                <td style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                  <button
                    className="btn btn--sm"
                    onClick={() =>
                      void descargar(
                        api.ajustes.plantillasPresupuesto.descargarPatronUrl(p.id),
                        `${p.nombre}.docx`,
                      ).catch((err) => setError(err instanceof Error ? err.message : String(err)))
                    }
                  >
                    <Download size={14} aria-hidden="true" />
                    Descargar patrón
                  </button>
                  {!p.es_sistema && (
                    <button className="btn btn--sm btn--danger" onClick={() => void eliminar(p)}>
                      <Trash2 size={14} aria-hidden="true" />
                      Eliminar
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {plantillas.length === 0 && (
              <tr>
                <td colSpan={3} className="muted">
                  Sin plantillas todavía.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
