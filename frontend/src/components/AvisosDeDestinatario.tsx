import { useCallback, useEffect, useState } from 'react'
import { Save } from 'lucide-react'

import { ErrorNotice, Field } from './ui'
import { api } from '../lib/api'
import type {
  CanalAviso,
  PreferenciaAvisos,
  SuscripcionAviso,
  TipoEvento,
} from '../lib/api'
import { useToast } from '../toast'

const CANALES: [CanalAviso, string][] = [
  ['campana', 'Campana'],
  ['email', 'Correo'],
  ['whatsapp', 'WhatsApp'],
]

/** Qué avisos recibe una persona o un grupo, y por dónde.
 *
 *  Vive dentro de la ficha de cada uno y no en una pantalla aparte: la
 *  pregunta «¿de qué quiero que se entere este grupo?» te la haces mirando
 *  al grupo, no en un listado de reglas. Cada casilla se guarda al tocarla:
 *  un botón de Guardar al final invitaría a marcar diez cosas y perderlas al
 *  cerrar sin querer. */
export function AvisosDeDestinatario({
  usuarioSubject,
  grupoId,
}: {
  usuarioSubject?: string
  grupoId?: string
}) {
  const { notificar } = useToast()
  const [eventos, setEventos] = useState<TipoEvento[]>([])
  const [suscripciones, setSuscripciones] = useState<SuscripcionAviso[]>([])
  const [preferencia, setPreferencia] = useState<PreferenciaAvisos | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [disponible, setDisponible] = useState(true)
  const [ocupado, setOcupado] = useState<string | null>(null)

  const de = usuarioSubject ? { usuario_subject: usuarioSubject } : { grupo_id: grupoId! }

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const [ev, sus] = await Promise.all([
        api.avisos.eventos(),
        api.avisos.suscripciones.list(
          usuarioSubject ? { usuario_subject: usuarioSubject } : { grupo_id: grupoId! },
        ),
      ])
      setEventos(ev)
      setSuscripciones(sus)
      if (usuarioSubject) setPreferencia(await api.avisos.preferenciasDe.get(usuarioSubject))
    } catch {
      // El módulo puede no estar activo en esta organización: no es un error
      // que enseñar, simplemente aquí no hay nada que configurar.
      setDisponible(false)
    } finally {
      setCargando(false)
    }
  }, [usuarioSubject, grupoId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const suscripcionDe = (codigo: string) =>
    suscripciones.find((s) => s.tipo_evento === codigo)

  /** Guarda la suscripción de un evento. Sin canales, el servidor la borra. */
  async function guardar(
    evento: TipoEvento,
    canales: CanalAviso[],
    parametros: Record<string, number>,
  ) {
    setOcupado(evento.codigo)
    setError(null)
    try {
      const guardada = await api.avisos.suscripciones.guardar({
        ...de,
        tipo_evento: evento.codigo,
        canales,
        parametros,
      })
      setSuscripciones((previas) => {
        const resto = previas.filter((s) => s.tipo_evento !== evento.codigo)
        return guardada ? [...resto, guardada] : resto
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      // Se recarga para que la pantalla no se quede enseñando algo que el
      // servidor no llegó a aceptar.
      await cargar()
    } finally {
      setOcupado(null)
    }
  }

  function alternarCanal(evento: TipoEvento, canal: CanalAviso) {
    const actual = suscripcionDe(evento.codigo)
    const canales = actual?.canales ?? []
    const nuevos = canales.includes(canal)
      ? canales.filter((c) => c !== canal)
      : [...canales, canal]
    const parametros =
      actual?.parametros ??
      Object.fromEntries(evento.parametros.map((p) => [p.nombre, p.por_defecto]))
    void guardar(evento, nuevos, parametros)
  }

  async function guardarPreferencia() {
    if (!preferencia || !usuarioSubject) return
    setError(null)
    try {
      setPreferencia(await api.avisos.preferenciasDe.update(usuarioSubject, preferencia))
      notificar('Guardado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  if (!disponible) {
    return <p className="muted">El módulo de Notificaciones no está activo en esta organización.</p>
  }
  if (cargando) return <p className="muted">Cargando…</p>
  if (eventos.length === 0) {
    return <p className="muted">No hay avisos disponibles para los módulos activos.</p>
  }

  return (
    <div>
      <ErrorNotice error={error} />
      <p className="form-section__note">
        Marca por dónde debe llegar cada aviso. Se guarda al momento.
        {usuarioSubject &&
          ' Además puede llegarle por los grupos a los que pertenezca, aunque aquí no esté marcado.'}
      </p>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Avisar de</th>
              {CANALES.map(([canal, texto]) => (
                <th key={canal} style={{ width: 90, textAlign: 'center' }}>
                  {texto}
                </th>
              ))}
              <th style={{ width: 150 }}>Cuándo</th>
            </tr>
          </thead>
          <tbody>
            {eventos.map((evento) => {
              const suscripcion = suscripcionDe(evento.codigo)
              const parametro = evento.parametros[0]
              return (
                <tr key={evento.codigo}>
                  <td>
                    {evento.etiqueta}
                    <div className="muted" style={{ fontSize: '0.85em' }}>
                      {evento.descripcion}
                    </div>
                  </td>
                  {CANALES.map(([canal]) => (
                    <td key={canal} style={{ textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        aria-label={`${evento.etiqueta} por ${canal}`}
                        checked={suscripcion?.canales.includes(canal) ?? false}
                        disabled={ocupado === evento.codigo}
                        onChange={() => alternarCanal(evento, canal)}
                      />
                    </td>
                  ))}
                  <td>
                    {parametro ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <input
                          className="input"
                          type="number"
                          min={parametro.minimo}
                          max={parametro.maximo}
                          style={{ width: 80 }}
                          // Sin suscripción el plazo no se puede tocar: no
                          // hay nada que guardar hasta que se elija un canal.
                          disabled={!suscripcion || ocupado === evento.codigo}
                          value={
                            suscripcion?.parametros?.[parametro.nombre] ?? parametro.por_defecto
                          }
                          onChange={(e) =>
                            suscripcion &&
                            void guardar(evento, suscripcion.canales, {
                              ...suscripcion.parametros,
                              [parametro.nombre]: Number(e.target.value),
                            })
                          }
                        />
                        <span className="muted" style={{ fontSize: '0.85em' }}>
                          {parametro.sufijo}
                        </span>
                      </div>
                    ) : (
                      <span className="muted" style={{ fontSize: '0.85em' }}>
                        Al momento
                      </span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {usuarioSubject && preferencia && (
        <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
          <Field
            ancho="doble"
            label="Móvil"
            hint="Para los avisos por WhatsApp. Sin él, ese canal no le llega."
          >
            <input
              className="input"
              type="tel"
              placeholder="+34 600 11 22 33"
              value={preferencia.telefono ?? ''}
              onChange={(e) => setPreferencia({ ...preferencia, telefono: e.target.value || null })}
            />
          </Field>
          <div className="field">
            <label className="checkbox" style={{ marginTop: 26 }}>
              <input
                type="checkbox"
                checked={preferencia.silenciado}
                onChange={(e) => setPreferencia({ ...preferencia, silenciado: e.target.checked })}
              />
              <span>
                Silenciado{' '}
                <span className="muted" style={{ fontSize: '0.85em' }}>
                  — la campana se sigue llenando
                </span>
              </span>
            </label>
          </div>
          <div className="field field--completo">
            <button className="btn btn--sm btn--primary" onClick={() => void guardarPreferencia()}>
              <Save size={14} aria-hidden="true" /> Guardar móvil y silencio
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
