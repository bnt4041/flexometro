import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { EmptyState, ErrorNotice, Tooltip } from './ui'
import { api } from '../lib/api'
import type { EntidadNota, Nota } from '../lib/api'

function formatoFecha(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Pestaña "CRM" (Fase 29) de cualquier objeto grande del negocio — un
 *  cuaderno de bitácora en forma de timeline, no de formulario: cada nota es
 *  un texto libre con quién la escribió y cuándo, sin más edición posible
 *  que borrarla. */
export function NotasCrm({ entidad, entidadId }: { entidad: EntidadNota; entidadId: string }) {
  const [notas, setNotas] = useState<Nota[]>([])
  const [borrador, setBorrador] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setNotas(await api.notas.list(entidad, entidadId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entidad, entidadId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function anadir() {
    if (borrador.trim() === '') return
    setGuardando(true)
    setError(null)
    try {
      await api.notas.create(entidad, entidadId, borrador.trim())
      setBorrador('')
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar(nota: Nota) {
    if (!window.confirm('¿Eliminar esta nota? No se puede deshacer.')) return
    try {
      await api.notas.remove(nota.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <>
      <ErrorNotice error={error} />

      <div className="card">
        <div className="form-section">
          <textarea
            className="input"
            rows={3}
            placeholder="Escribe una nota de seguimiento…"
            value={borrador}
            onChange={(e) => setBorrador(e.target.value)}
          />
          <div className="form-actions">
            <Tooltip texto="Añadir esta nota al historial">
              <button
                className="btn btn--primary"
                disabled={borrador.trim() === '' || guardando}
                onClick={() => void anadir()}
              >
                <Plus size={16} aria-hidden="true" />
                {guardando ? 'Añadiendo…' : 'Añadir nota'}
              </button>
            </Tooltip>
          </div>
        </div>
      </div>

      {notas.length === 0 ? (
        <EmptyState title="Sin notas todavía">
          Apunta aquí llamadas, acuerdos o cualquier cosa que el equipo deba recordar.
        </EmptyState>
      ) : (
        <div className="timeline">
          {notas.map((n) => (
            <div key={n.id} className="timeline__item">
              <div className="timeline__meta">
                <span>{n.creado_por_nombre ?? 'Alguien'}</span>
                <span className="muted"> · {formatoFecha(n.created_at)}</span>
              </div>
              <div className="timeline__cuerpo">{n.contenido}</div>
              <Tooltip texto="Eliminar esta nota">
                <button
                  className="btn btn--sm btn--danger btn--solo-icono timeline__eliminar"
                  onClick={() => void eliminar(n)}
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </Tooltip>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
