import { useCallback, useEffect, useState } from 'react'
import { Mail, Paperclip, Plus, Trash2 } from 'lucide-react'

import { EnviarEmailModal } from './EnviarEmailModal'
import { EmptyState, ErrorNotice, Tooltip } from './ui'
import { api, descargar } from '../lib/api'
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
  const [enviandoEmail, setEnviandoEmail] = useState(false)

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
            <Tooltip texto="Redactar y enviar un correo, vinculado a esta ficha">
              <button className="btn" onClick={() => setEnviandoEmail(true)}>
                <Mail size={16} aria-hidden="true" />
                Enviar email
              </button>
            </Tooltip>
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

      {enviandoEmail && (
        <EnviarEmailModal
          entidad={entidad}
          entidadId={entidadId}
          onClose={() => setEnviandoEmail(false)}
          onEnviado={() => {
            setEnviandoEmail(false)
            void cargar()
          }}
        />
      )}

      {notas.length === 0 ? (
        <EmptyState title="Sin notas todavía">
          Apunta aquí llamadas, acuerdos o cualquier cosa que el equipo deba recordar.
        </EmptyState>
      ) : (
        <div className="timeline">
          {notas.map((n) => (
            <div key={n.id} className="timeline__item">
              <div className="timeline__meta">
                {n.tipo === 'email' && (
                  <span className="badge badge--info" style={{ marginRight: 'var(--sp-2)' }}>
                    <Mail size={11} aria-hidden="true" /> Email
                  </span>
                )}
                <span>{n.creado_por_nombre ?? 'Alguien'}</span>
                <span className="muted"> · {formatoFecha(n.created_at)}</span>
              </div>
              {n.tipo === 'email' ? (
                <>
                  <div style={{ fontSize: 'var(--fs-sm)', marginBottom: 'var(--sp-1)' }}>
                    <strong>Para:</strong> {n.destinatario} — <strong>{n.asunto}</strong>
                  </div>
                  <div className="timeline__cuerpo" dangerouslySetInnerHTML={{ __html: n.contenido }} />
                  {n.adjuntos.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)' }}>
                      {n.adjuntos.map((a, i) =>
                        a.documento_id ? (
                          <button
                            key={a.documento_id}
                            type="button"
                            className="badge"
                            onClick={() =>
                              void descargar(api.documentos.descargarUrl(a.documento_id as string), a.nombre_archivo)
                            }
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 'var(--sp-1)',
                              border: 'none',
                              cursor: 'pointer',
                            }}
                          >
                            <Paperclip size={11} aria-hidden="true" />
                            {a.nombre_archivo}
                          </button>
                        ) : (
                          <Tooltip key={`${a.nombre_archivo}-${i}`} texto="No se guardó en la ficha, solo se envió">
                            <span
                              className="badge"
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--sp-1)', opacity: 0.7 }}
                            >
                              <Paperclip size={11} aria-hidden="true" />
                              {a.nombre_archivo}
                            </span>
                          </Tooltip>
                        ),
                      )}
                    </div>
                  )}
                </>
              ) : (
                <div className="timeline__cuerpo">{n.contenido}</div>
              )}
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
