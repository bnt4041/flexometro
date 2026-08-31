import { useCallback, useEffect, useState } from 'react'
import { Copy, Key, Plus, RefreshCw, Trash2, Webhook } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla } from '../components/ui'
import { api } from '../lib/api'
import type {
  Alcance,
  AmbitoModulo,
  ClaveApi,
  EntregaWebhook,
  EventoWebhook,
  ModuloDisponible,
  WebhookSuscripcion,
} from '../lib/api'
import { useToast } from '../toast'

const ACCIONES: [keyof AmbitoModulo, string][] = [
  ['ver', 'Ver'],
  ['editar', 'Modificar'],
  ['crear', 'Crear'],
  ['borrar', 'Borrar'],
]

const VACIO: AmbitoModulo = { ver: 'ninguno', editar: 'ninguno', crear: 'ninguno', borrar: 'ninguno' }

/** Claves de API y webhooks. */
export function Desarrolladores() {
  const [pestana, setPestana] = useState<'claves' | 'webhooks'>('claves')

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Desarrolladores</h1>
          <p className="page-lead">
            Claves para entrar sin navegador y webhooks para que otros sistemas se enteren de lo
            que pasa aquí. Una clave nunca puede hacer más de lo que le concedas.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)' }}>
        <button
          className={`btn btn--sm${pestana === 'claves' ? ' btn--primary' : ''}`}
          onClick={() => setPestana('claves')}
        >
          <Key size={14} aria-hidden="true" /> Claves de API
        </button>
        <button
          className={`btn btn--sm${pestana === 'webhooks' ? ' btn--primary' : ''}`}
          onClick={() => setPestana('webhooks')}
        >
          <Webhook size={14} aria-hidden="true" /> Webhooks
        </button>
      </div>

      {pestana === 'claves' ? <Claves /> : <Webhooks />}
    </div>
  )
}

function Claves() {
  const { notificar } = useToast()
  const [claves, setClaves] = useState<ClaveApi[]>([])
  const [modulos, setModulos] = useState<ModuloDisponible[]>([])
  const [error, setError] = useState<string | null>(null)
  const [creando, setCreando] = useState(false)
  const [reciencreada, setRecienCreada] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setClaves(await api.desarrolladores.claves.list())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
    api.usuariosYGrupos
      .modulosDisponibles()
      .then(setModulos)
      .catch(() => setModulos([]))
  }, [cargar])

  async function revocar(clave: ClaveApi) {
    if (!window.confirm(`¿Revocar «${clave.nombre}»? Lo que la use dejará de funcionar al momento.`))
      return
    await api.desarrolladores.claves.remove(clave.id).catch(() => undefined)
    notificar('Clave revocada')
    await cargar()
  }

  return (
    <div>
      <ErrorNotice error={error} />

      {reciencreada && (
        <div className="notice" style={{ marginBottom: 'var(--sp-4)' }}>
          <strong>Cópiala ahora.</strong> De la clave solo se guarda su huella, así que esta es la
          única vez que se puede ver.
          <div style={{ display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)' }}>
            <input className="input" readOnly value={reciencreada} onFocus={(e) => e.currentTarget.select()} />
            <button
              className="btn btn--sm"
              onClick={() => {
                void navigator.clipboard.writeText(reciencreada).then(() => notificar('Copiada'))
              }}
            >
              <Copy size={14} aria-hidden="true" /> Copiar
            </button>
            <button className="btn btn--sm" onClick={() => setRecienCreada(null)}>
              Ya la tengo
            </button>
          </div>
        </div>
      )}

      <div style={{ marginBottom: 'var(--sp-3)' }}>
        <button className="btn btn--primary" onClick={() => setCreando(true)}>
          <Plus size={16} aria-hidden="true" /> Nueva clave
        </button>
      </div>

      {claves.length === 0 ? (
        <EmptyState title="Sin claves">
          Crea una para que otro sistema pueda leer o escribir en Flexómetro.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Clave</th>
                <th>Puede</th>
                <th>Último uso</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {claves.map((clave) => (
                <tr key={clave.id}>
                  <td>
                    {clave.nombre}
                    {!clave.activa && <span className="badge" style={{ marginLeft: 6 }}>revocada</span>}
                  </td>
                  <td>
                    <code>flx_{clave.prefijo}…</code>
                  </td>
                  <td className="muted" style={{ fontSize: '0.85em' }}>
                    {Object.keys(clave.ambitos).length === 0
                      ? 'Nada'
                      : Object.entries(clave.ambitos)
                          .map(([m, a]) => `${m} (${ACCIONES.filter(([k]) => a[k] !== 'ninguno').map(([, t]) => t.toLowerCase()).join('/')})`)
                          .join(', ')}
                  </td>
                  <td className="muted" style={{ fontSize: '0.85em' }}>
                    {clave.ultimo_uso_en
                      ? new Date(clave.ultimo_uso_en).toLocaleString()
                      : 'Nunca usada'}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn--sm btn--danger"
                      onClick={() => void revocar(clave)}
                      aria-label={`Revocar ${clave.nombre}`}
                    >
                      <Trash2 size={13} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creando && (
        <NuevaClave
          modulos={modulos}
          onCerrar={() => setCreando(false)}
          onCreada={async (clave) => {
            setCreando(false)
            setRecienCreada(clave)
            await cargar()
          }}
        />
      )}
    </div>
  )
}

function NuevaClave({
  modulos,
  onCerrar,
  onCreada,
}: {
  modulos: ModuloDisponible[]
  onCerrar: () => void
  onCreada: (clave: string) => void | Promise<void>
}) {
  const [nombre, setNombre] = useState('')
  const [dias, setDias] = useState('')
  const [ambitos, setAmbitos] = useState<Record<string, AmbitoModulo>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function crear() {
    if (!nombre.trim()) {
      setError('Ponle un nombre: es lo que verás en la lista y en la auditoría.')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      const creada = await api.desarrolladores.claves.create({
        nombre: nombre.trim(),
        ambitos,
        dias_validez: dias ? Number(dias) : null,
      })
      await onCreada(creada.clave)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    // A pantalla completa y no en diálogo pequeño: la rejilla de ámbitos es
    // la misma tabla de 5 columnas que los permisos de un grupo, y en un
    // diálogo estrecho los desplegables se cortan («Ningu…»).
    <ModalPantalla title="Nueva clave de API" onClose={onCerrar} elevado>
      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field ancho="doble" label="Nombre" hint="Para qué es: «ERP de contabilidad», «app de obra»">
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus />
          </Field>
          <Field label="Caduca en (días)" hint="En blanco, no caduca">
            <input
              className="input"
              type="number"
              min={1}
              value={dias}
              onChange={(e) => setDias(e.target.value)}
            />
          </Field>
        </div>

        <div className="form-section__title" style={{ marginTop: 'var(--sp-4)' }}>
          Qué puede hacer
        </div>
        <p className="form-section__note">
          Lo mismo que los permisos de una persona. Deja en «ninguno» todo lo que no necesite: una
          clave filtrada solo llega hasta donde le hayas dejado.
        </p>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Módulo</th>
                {ACCIONES.map(([a, texto]) => (
                  <th key={a}>{texto}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {modulos.map((modulo) => (
                <tr key={modulo.code}>
                  <td>{modulo.name}</td>
                  {ACCIONES.map(([accion]) => (
                    <td key={accion}>
                      <select
                        className="select"
                        value={ambitos[modulo.code]?.[accion] ?? 'ninguno'}
                        onChange={(e) =>
                          setAmbitos((previo) => ({
                            ...previo,
                            [modulo.code]: {
                              ...(previo[modulo.code] ?? VACIO),
                              [accion]: e.target.value as Alcance,
                            },
                          }))
                        }
                      >
                        {(accion === 'crear'
                          ? (['ninguno', 'todos'] as Alcance[])
                          : (['ninguno', 'propios', 'todos'] as Alcance[])
                        ).map((v) => (
                          <option key={v} value={v}>
                            {accion === 'crear'
                              ? v === 'ninguno'
                                ? 'No'
                                : 'Sí'
                              : v === 'ninguno'
                                ? 'Ninguno'
                                : v === 'propios'
                                  ? 'Los suyos'
                                  : 'Todos'}
                          </option>
                        ))}
                      </select>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      <div className="form-actions">
        <button className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button className="btn btn--primary" onClick={() => void crear()} disabled={guardando}>
          {guardando ? 'Creando…' : 'Crear clave'}
        </button>
      </div>
      </div>
    </ModalPantalla>
  )
}

function Webhooks() {
  const { notificar } = useToast()
  const [webhooks, setWebhooks] = useState<WebhookSuscripcion[]>([])
  const [eventos, setEventos] = useState<EventoWebhook[]>([])
  const [entregas, setEntregas] = useState<EntregaWebhook[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editando, setEditando] = useState<WebhookSuscripcion | 'nuevo' | null>(null)

  const cargar = useCallback(async () => {
    try {
      const [wh, ev] = await Promise.all([
        api.desarrolladores.webhooks.list(),
        api.desarrolladores.eventos(),
      ])
      setWebhooks(wh)
      setEventos(ev)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div>
      <ErrorNotice error={error} />
      <div style={{ marginBottom: 'var(--sp-3)' }}>
        <button className="btn btn--primary" onClick={() => setEditando('nuevo')}>
          <Plus size={16} aria-hidden="true" /> Nuevo webhook
        </button>
      </div>

      {webhooks.length === 0 ? (
        <EmptyState title="Sin webhooks">
          Avisa a otro sistema cuando pase algo aquí: una firma completada, una oferta recibida…
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>URL</th>
                <th>Eventos</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {webhooks.map((wh) => (
                <tr key={wh.id}>
                  <td>
                    <button className="btn-enlace" onClick={() => setEditando(wh)}>
                      {wh.nombre}
                    </button>
                    {!wh.activa && <span className="badge" style={{ marginLeft: 6 }}>parado</span>}
                  </td>
                  <td className="muted" style={{ fontSize: '0.85em', wordBreak: 'break-all' }}>
                    {wh.url}
                  </td>
                  <td className="muted" style={{ fontSize: '0.85em' }}>
                    {wh.eventos.length} evento{wh.eventos.length === 1 ? '' : 's'}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn--sm"
                      onClick={() =>
                        void api.desarrolladores.webhooks
                          .entregas(wh.id)
                          .then(setEntregas)
                          .catch(() => setEntregas([]))
                      }
                    >
                      Ver envíos
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editando && (
        <EditorWebhook
          webhook={editando === 'nuevo' ? null : editando}
          eventos={eventos}
          onCerrar={() => setEditando(null)}
          onGuardado={async () => {
            setEditando(null)
            await cargar()
          }}
        />
      )}

      {entregas && (
        <Modal title="Últimos envíos" onClose={() => setEntregas(null)}>
          <div className="form-section">
            {entregas.length === 0 ? (
              <p className="muted">Todavía no se ha mandado nada.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Cuándo</th>
                    <th>Evento</th>
                    <th>Estado</th>
                    <th>Intentos</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {entregas.map((e) => (
                    <tr key={e.id}>
                      <td className="muted" style={{ fontSize: '0.85em' }}>
                        {new Date(e.created_at).toLocaleString()}
                      </td>
                      <td>{e.evento}</td>
                      <td>
                        <span
                          className={`notice ${
                            e.estado === 'entregada'
                              ? 'notice--ok'
                              : e.estado === 'agotada'
                                ? 'notice--error'
                                : 'notice--aviso'
                          }`}
                          style={{ margin: 0, padding: '1px 7px', fontSize: '0.8em' }}
                        >
                          {e.estado}
                          {e.respuesta_codigo ? ` · ${e.respuesta_codigo}` : ''}
                        </span>
                        {e.error && (
                          <div className="muted" style={{ fontSize: '0.8em' }}>
                            {e.error.slice(0, 120)}
                          </div>
                        )}
                      </td>
                      <td>{e.intentos}</td>
                      <td style={{ textAlign: 'right' }}>
                        {e.estado === 'agotada' && (
                          <button
                            className="btn btn--sm"
                            onClick={() =>
                              void api.desarrolladores.webhooks.reintentar(e.id).then(() => {
                                notificar('Vuelto a poner en cola')
                                setEntregas(null)
                              })
                            }
                          >
                            <RefreshCw size={13} aria-hidden="true" /> Reintentar
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}

function EditorWebhook({
  webhook,
  eventos,
  onCerrar,
  onGuardado,
}: {
  webhook: WebhookSuscripcion | null
  eventos: EventoWebhook[]
  onCerrar: () => void
  onGuardado: () => void | Promise<void>
}) {
  const { notificar } = useToast()
  const [nombre, setNombre] = useState(webhook?.nombre ?? '')
  const [url, setUrl] = useState(webhook?.url ?? '')
  const [activa, setActiva] = useState(webhook?.activa ?? true)
  const [elegidos, setElegidos] = useState<string[]>(webhook?.eventos ?? [])
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar() {
    if (elegidos.length === 0) {
      setError('Elige al menos un evento: un webhook sin eventos no manda nada.')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      if (webhook)
        await api.desarrolladores.webhooks.update(webhook.id, {
          nombre, url, eventos: elegidos, activa,
        })
      else await api.desarrolladores.webhooks.create({ nombre, url, eventos: elegidos, activa })
      notificar('Guardado')
      await onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal title={webhook ? `Webhook «${webhook.nombre}»` : 'Nuevo webhook'} onClose={onCerrar}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field label="Nombre">
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Field>
          <Field label="Activo">
            <select className="select" value={activa ? 'si' : 'no'} onChange={(e) => setActiva(e.target.value === 'si')}>
              <option value="si">Sí</option>
              <option value="no">No</option>
            </select>
          </Field>
          <Field ancho="completo" label="URL" hint="Tiene que ser https: el cuerpo lleva datos de negocio">
            <input className="input" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
          </Field>
        </div>

        {webhook && (
          <Field ancho="completo" label="Secreto de firma" hint="Configúralo en el otro extremo para verificar cada envío">
            <input className="input" readOnly value={webhook.secreto} onFocus={(e) => e.currentTarget.select()} />
          </Field>
        )}

        <div className="form-section__title" style={{ marginTop: 'var(--sp-4)' }}>
          Avisar cuando
        </div>
        {eventos.map((evento) => (
          <label key={evento.codigo} className="checkbox" style={{ display: 'block', marginTop: 6 }}>
            <input
              type="checkbox"
              checked={elegidos.includes(evento.codigo)}
              onChange={() =>
                setElegidos((previos) =>
                  previos.includes(evento.codigo)
                    ? previos.filter((c) => c !== evento.codigo)
                    : [...previos, evento.codigo],
                )
              }
            />
            <span>
              {evento.etiqueta}{' '}
              <code className="muted" style={{ fontSize: '0.8em' }}>
                {evento.codigo}
              </code>
            </span>
          </label>
        ))}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button className="btn btn--primary" onClick={() => void guardar()} disabled={guardando}>
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </Modal>
  )
}
