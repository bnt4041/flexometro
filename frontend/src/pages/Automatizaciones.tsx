import { useCallback, useEffect, useState } from 'react'
import { Play, Plus, Save, Trash2 } from 'lucide-react'

import { LienzoFlujo } from '../components/LienzoFlujo'
import { EmptyState, ErrorNotice, Field, Modal } from '../components/ui'
import { api } from '../lib/api'
import type {
  Automatizacion,
  DefinicionFlujo,
  EjecucionFlujo,
  EventoWebhook,
  Grupo,
  TipoNodo,
} from '../lib/api'
import { useToast } from '../toast'

const VACIA: DefinicionFlujo = { nodos: [], conexiones: [] }

/** Flujos de nodos que se disparan solos. */
export function Automatizaciones() {
  const { notificar } = useToast()
  const [flujos, setFlujos] = useState<Automatizacion[]>([])
  const [abierto, setAbierto] = useState<Automatizacion | 'nuevo' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      setFlujos(await api.automatizaciones.list())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function borrar(flujo: Automatizacion) {
    if (!window.confirm(`¿Borrar «${flujo.nombre}»? Se pierde también su histórico.`)) return
    await api.automatizaciones.remove(flujo.id).catch(() => undefined)
    notificar('Flujo borrado')
    await cargar()
  }

  if (abierto) {
    return (
      <EditorFlujo
        flujo={abierto === 'nuevo' ? null : abierto}
        onCerrar={() => setAbierto(null)}
        onGuardado={async () => {
          setAbierto(null)
          await cargar()
        }}
      />
    )
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Automatizaciones</h1>
          <p className="page-lead">
            Flujos que se disparan solos: cuando pasa algo, cuando llaman a una URL o cada cierto
            tiempo. Cada nodo recibe lo que produjeron los anteriores y decide por qué rama sigue.
          </p>
        </div>
        <button className="btn btn--primary" onClick={() => setAbierto('nuevo')}>
          <Plus size={16} aria-hidden="true" /> Nuevo flujo
        </button>
      </div>

      <ErrorNotice error={error} />

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : flujos.length === 0 ? (
        <EmptyState title="Sin flujos">
          Monta el primero: «cuando una obra lleve 90 días parada, avisa a los jefes de obra».
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Flujo</th>
                <th>Arranca</th>
                <th>Nodos</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {flujos.map((flujo) => (
                <tr key={flujo.id}>
                  <td>
                    <button className="btn-enlace" onClick={() => setAbierto(flujo)}>
                      {flujo.nombre}
                    </button>
                    {flujo.descripcion && (
                      <div className="muted" style={{ fontSize: '0.85em' }}>
                        {flujo.descripcion}
                      </div>
                    )}
                  </td>
                  <td className="muted" style={{ fontSize: '0.85em' }}>
                    {flujo.evento_disparador ?? '—'}
                  </td>
                  <td>{flujo.definicion?.nodos?.length ?? 0}</td>
                  <td>
                    {flujo.activa ? (
                      <span className="badge badge--success">activo</span>
                    ) : (
                      <span className="badge">parado</span>
                    )}
                    {flujo.problemas.length > 0 && (
                      <div
                        className="notice notice--aviso"
                        style={{ margin: '4px 0 0', padding: '1px 7px', fontSize: '0.78em' }}
                      >
                        {flujo.problemas[0]}
                      </div>
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn btn--sm btn--danger"
                      onClick={() => void borrar(flujo)}
                      aria-label={`Borrar ${flujo.nombre}`}
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
    </div>
  )
}

function EditorFlujo({
  flujo,
  onCerrar,
  onGuardado,
}: {
  flujo: Automatizacion | null
  onCerrar: () => void
  onGuardado: () => void | Promise<void>
}) {
  const { notificar } = useToast()
  const [tipos, setTipos] = useState<TipoNodo[]>([])
  const [eventos, setEventos] = useState<EventoWebhook[]>([])
  const [grupos, setGrupos] = useState<Grupo[]>([])
  const [nombre, setNombre] = useState(flujo?.nombre ?? '')
  const [descripcion, setDescripcion] = useState(flujo?.descripcion ?? '')
  const [activa, setActiva] = useState(flujo?.activa ?? false)
  const [definicion, setDefinicion] = useState<DefinicionFlujo>(flujo?.definicion ?? VACIA)
  const [seleccionado, setSeleccionado] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [ultima, setUltima] = useState<EjecucionFlujo | null>(null)
  const [urlWebhook, setUrlWebhook] = useState<string | null>(flujo?.url_webhook ?? null)

  useEffect(() => {
    void api.automatizaciones.nodos().then(setTipos).catch(() => setTipos([]))
    void api.desarrolladores
      .eventos()
      .then(setEventos)
      .catch(() => setEventos([]))
    void api.usuariosYGrupos.grupos
      .list()
      .then(setGrupos)
      .catch(() => setGrupos([]))
  }, [])

  const nodo = definicion.nodos.find((n) => n.id === seleccionado) ?? null
  const tipoDelNodo = tipos.find((t) => t.tipo === nodo?.tipo) ?? null

  function anadirNodo(tipo: TipoNodo) {
    const id = `n${Date.now().toString(36)}`
    setDefinicion((previa) => ({
      ...previa,
      nodos: [
        ...previa.nodos,
        {
          id,
          tipo: tipo.tipo,
          nombre: tipo.etiqueta,
          parametros: Object.fromEntries(
            tipo.campos.filter((c) => c.por_defecto != null).map((c) => [c.nombre, c.por_defecto]),
          ),
          // En cascada, para que no se apilen unos encima de otros.
          x: 40 + (previa.nodos.length % 4) * 240,
          y: 40 + Math.floor(previa.nodos.length / 4) * 120,
        },
      ],
    }))
    setSeleccionado(id)
  }

  function cambiarParametro(campo: string, valor: unknown) {
    if (!nodo) return
    setDefinicion((previa) => ({
      ...previa,
      nodos: previa.nodos.map((n) =>
        n.id === nodo.id ? { ...n, parametros: { ...(n.parametros ?? {}), [campo]: valor } } : n,
      ),
    }))
  }

  async function guardar() {
    if (!nombre.trim()) {
      setError('Ponle un nombre al flujo.')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      const datos = { nombre: nombre.trim(), descripcion: descripcion || null, activa, definicion }
      const guardado = flujo
        ? await api.automatizaciones.update(flujo.id, datos)
        : await api.automatizaciones.create(datos)
      if (guardado.url_webhook) setUrlWebhook(guardado.url_webhook)
      notificar('Flujo guardado')
      // Con URL de webhook nueva NO se cierra: es la única vez que se ve.
      if (!guardado.url_webhook) await onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function probar() {
    if (!flujo) {
      setError('Guarda el flujo antes de probarlo.')
      return
    }
    setError(null)
    try {
      setUltima(await api.automatizaciones.probar(flujo.id, {}))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const pasosPorNodo = Object.fromEntries(
    (ultima?.pasos ?? []).map((p) => [p.nodo_id, { estado: p.estado, ruta: p.ruta }]),
  )

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">{flujo ? flujo.nombre : 'Nuevo flujo'}</h1>
          <p className="page-lead">
            Añade nodos, pulsa el punto de una salida y luego el nodo de destino para conectarlos.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <button className="btn" onClick={onCerrar}>
            Volver
          </button>
          {flujo && (
            <button className="btn" onClick={() => void probar()}>
              <Play size={16} aria-hidden="true" /> Probar
            </button>
          )}
          <button className="btn btn--primary" onClick={() => void guardar()} disabled={guardando}>
            <Save size={16} aria-hidden="true" /> {guardando ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      </div>

      <ErrorNotice error={error} />

      {urlWebhook && (
        <div className="notice" style={{ marginBottom: 'var(--sp-3)' }}>
          <strong>Ésta es la URL del flujo.</strong> Cópiala ahora: del token solo se guarda su
          huella, así que no se puede volver a enseñar.
          <input
            className="input"
            readOnly
            value={urlWebhook}
            onFocus={(e) => e.currentTarget.select()}
            style={{ marginTop: 'var(--sp-2)' }}
          />
        </div>
      )}

      <div className="form-grid" style={{ marginBottom: 'var(--sp-3)' }}>
        <Field ancho="doble" label="Nombre">
          <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </Field>
        <Field label="Activo" hint="Un flujo con problemas no se puede activar">
          <select
            className="select"
            value={activa ? 'si' : 'no'}
            onChange={(e) => setActiva(e.target.value === 'si')}
          >
            <option value="no">No</option>
            <option value="si">Sí</option>
          </select>
        </Field>
        <Field ancho="completo" label="Descripción" hint="Para qué es, en una línea">
          <input
            className="input"
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
          />
        </Field>
      </div>

      <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap', marginBottom: 'var(--sp-2)' }}>
        {tipos.map((tipo) => (
          <button
            key={tipo.tipo}
            className="btn btn--sm"
            title={tipo.descripcion}
            onClick={() => anadirNodo(tipo)}
          >
            <Plus size={13} aria-hidden="true" /> {tipo.etiqueta}
          </button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 'var(--sp-3)' }}>
        <LienzoFlujo
          definicion={definicion}
          tipos={tipos}
          seleccionado={seleccionado}
          onSeleccionar={setSeleccionado}
          onCambio={setDefinicion}
          pasosPorNodo={pasosPorNodo}
        />

        <div className="card" style={{ padding: 'var(--sp-4)', alignSelf: 'start' }}>
          {!nodo || !tipoDelNodo ? (
            <p className="muted" style={{ margin: 0 }}>
              Pulsa un nodo para configurarlo.
            </p>
          ) : (
            <>
              <div className="form-section__title">{tipoDelNodo.etiqueta}</div>
              <p className="form-section__note">{tipoDelNodo.descripcion}</p>

              <Field label="Nombre del nodo">
                <input
                  className="input"
                  value={nodo.nombre ?? ''}
                  onChange={(e) =>
                    setDefinicion((previa) => ({
                      ...previa,
                      nodos: previa.nodos.map((n) =>
                        n.id === nodo.id ? { ...n, nombre: e.target.value } : n,
                      ),
                    }))
                  }
                />
              </Field>

              {tipoDelNodo.campos.map((campo) => {
                const valor = (nodo.parametros ?? {})[campo.nombre] ?? ''
                const opciones =
                  campo.nombre === 'evento'
                    ? eventos.map((e) => [e.codigo, e.etiqueta] as [string, string])
                    : campo.nombre === 'grupo_id'
                      ? grupos.map((g) => [g.id, g.nombre] as [string, string])
                      : campo.opciones
                return (
                  <Field
                    key={campo.nombre}
                    label={campo.etiqueta}
                    hint={
                      campo.ayuda ||
                      (campo.admite_expresiones ? 'Admite {{ disparador.campo }}' : undefined)
                    }
                  >
                    {campo.tipo === 'seleccion' ? (
                      <select
                        className="select"
                        value={String(valor)}
                        onChange={(e) => cambiarParametro(campo.nombre, e.target.value)}
                      >
                        <option value="">Elegir…</option>
                        {opciones.map(([v, t]) => (
                          <option key={v} value={v}>
                            {t}
                          </option>
                        ))}
                      </select>
                    ) : campo.tipo === 'texto_largo' ? (
                      <textarea
                        className="input"
                        rows={4}
                        value={String(valor)}
                        onChange={(e) => cambiarParametro(campo.nombre, e.target.value)}
                      />
                    ) : (
                      <input
                        className="input"
                        type={campo.tipo === 'numero' ? 'number' : 'text'}
                        value={String(valor)}
                        onChange={(e) =>
                          cambiarParametro(
                            campo.nombre,
                            campo.tipo === 'numero' ? Number(e.target.value) : e.target.value,
                          )
                        }
                      />
                    )}
                  </Field>
                )
              })}
            </>
          )}
        </div>
      </div>

      {ultima && (
        <Modal title="Resultado de la prueba" onClose={() => setUltima(null)}>
          <div className="form-section">
            <p>
              Estado: <strong>{ultima.estado}</strong>
              {ultima.error && ` — ${ultima.error}`}
            </p>
            <table className="table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Nodo</th>
                  <th>Resultado</th>
                  <th>Rama</th>
                  <th>ms</th>
                </tr>
              </thead>
              <tbody>
                {ultima.pasos.map((paso) => (
                  <tr key={paso.nodo_id}>
                    <td>{paso.orden}</td>
                    <td>{paso.tipo_nodo}</td>
                    <td>
                      {paso.estado}
                      {paso.error && (
                        <div className="muted" style={{ fontSize: '0.8em' }}>
                          {paso.error}
                        </div>
                      )}
                    </td>
                    <td>{paso.ruta ?? '—'}</td>
                    <td>{paso.duracion_ms ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
    </div>
  )
}
