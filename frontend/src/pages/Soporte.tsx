import { useCallback, useEffect, useMemo, useState } from 'react'
import { BookOpen, LifeBuoy, Plus, RefreshCw, Save, Search, Send, Trash2 } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal } from '../components/ui'
import { api } from '../lib/api'
import type {
  EstadoTicket,
  PaginaWiki,
  PrioridadTicket,
  ResultadoBusquedaWiki,
  Ticket,
  TipoTicket,
} from '../lib/api'
import { useToast } from '../toast'

const ESTADOS: Record<EstadoTicket, string> = {
  nuevo: 'Nuevo',
  abierto: 'En curso',
  esperando: 'Esperando respuesta',
  resuelto: 'Resuelto',
  cerrado: 'Cerrado',
}

const TIPOS: Record<TipoTicket, string> = {
  incidencia: 'Algo no funciona',
  peticion: 'Petición de mejora',
  duda: 'Duda de uso',
}

const PRIORIDADES: Record<PrioridadTicket, string> = {
  baja: 'Baja',
  normal: 'Normal',
  alta: 'Alta',
  urgente: 'Urgente',
}

/** Ayuda: tickets y wiki.
 *
 *  Las dos mitades no están juntas por casualidad. La wiki es lo que el
 *  asistente lee para responder (está indexada por significado), y un ticket
 *  resuelto suele ser material para una página nueva: lo que hoy se pregunta
 *  por ticket mañana debería estar escrito. */
export function Soporte() {
  const { notificar } = useToast()
  const [pestana, setPestana] = useState<'tickets' | 'wiki'>('tickets')

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Ayuda y tickets</h1>
          <p className="page-lead">
            Si algo no funciona o echas algo en falta, abre un ticket. Y lo que se pregunta
            una y otra vez, escríbelo en la wiki: es lo que lee el asistente para responder.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-4)' }}>
        <button
          type="button"
          className={`btn btn--sm${pestana === 'tickets' ? ' btn--primary' : ''}`}
          onClick={() => setPestana('tickets')}
        >
          <LifeBuoy size={14} aria-hidden="true" /> Tickets
        </button>
        <button
          type="button"
          className={`btn btn--sm${pestana === 'wiki' ? ' btn--primary' : ''}`}
          onClick={() => setPestana('wiki')}
        >
          <BookOpen size={14} aria-hidden="true" /> Wiki
        </button>
      </div>

      {pestana === 'tickets' ? <Tickets notificar={notificar} /> : <Wiki notificar={notificar} />}
    </div>
  )
}

type Notificar = ReturnType<typeof useToast>['notificar']

// ── Tickets ─────────────────────────────────────────────────────────────

function Tickets({ notificar }: { notificar: Notificar }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [abierto, setAbierto] = useState<Ticket | null>(null)
  const [nuevo, setNuevo] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      setTickets(await api.soporte.tickets.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const abiertos = tickets.filter((t) => t.estado !== 'cerrado' && t.estado !== 'resuelto')
  const cerrados = tickets.filter((t) => t.estado === 'cerrado' || t.estado === 'resuelto')

  return (
    <>
      <div className="toolbar" style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
        <button type="button" className="btn btn--primary" onClick={() => setNuevo(true)}>
          <Plus size={16} aria-hidden="true" /> Abrir ticket
        </button>
      </div>
      <ErrorNotice error={error} />

      {!cargando && tickets.length === 0 && (
        <EmptyState title="Ningún ticket todavía">
          Si algo no funciona o echas en falta algo, ábrelo aquí y queda registrado.
        </EmptyState>
      )}

      {abiertos.length > 0 && <ListaTickets titulo="Abiertos" tickets={abiertos} onAbrir={setAbierto} />}
      {cerrados.length > 0 && <ListaTickets titulo="Cerrados" tickets={cerrados} onAbrir={setAbierto} />}

      {nuevo && (
        <NuevoTicket
          onCerrar={() => setNuevo(false)}
          onCreado={(t) => {
            setNuevo(false)
            setTickets((prev) => [t, ...prev])
            setAbierto(t)
            notificar(`Ticket ${t.codigo} abierto`)
          }}
        />
      )}

      {abierto && (
        <DetalleTicket
          ticket={abierto}
          onCerrar={() => setAbierto(null)}
          onCambio={(t) => {
            setAbierto(t)
            setTickets((prev) => prev.map((x) => (x.id === t.id ? t : x)))
          }}
          notificar={notificar}
        />
      )}
    </>
  )
}

function ListaTickets({
  titulo,
  tickets,
  onAbrir,
}: {
  titulo: string
  tickets: Ticket[]
  onAbrir: (t: Ticket) => void
}) {
  return (
    <section className="form-section">
      <h2 className="form-section__title">{titulo}</h2>
      <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Código</th>
            <th>Asunto</th>
            <th>Tipo</th>
            <th>Estado</th>
            <th>Prioridad</th>
            <th>Abierto por</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id} onClick={() => onAbrir(t)} style={{ cursor: 'pointer' }}>
              <td>{t.codigo}</td>
              <td>{t.titulo}</td>
              <td>{TIPOS[t.tipo]}</td>
              <td>{ESTADOS[t.estado]}</td>
              <td>{PRIORIDADES[t.prioridad]}</td>
              <td>{t.creado_por_nombre ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  )
}

function NuevoTicket({
  onCerrar,
  onCreado,
}: {
  onCerrar: () => void
  onCreado: (t: Ticket) => void
}) {
  const [titulo, setTitulo] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [tipo, setTipo] = useState<TipoTicket>('incidencia')
  const [prioridad, setPrioridad] = useState<PrioridadTicket>('normal')
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar() {
    setEnviando(true)
    try {
      onCreado(
        await api.soporte.tickets.create({
          titulo,
          descripcion,
          tipo,
          prioridad,
          // De dónde viene: al que lo lea le ahorra la primera pregunta.
          ruta_origen: window.location.pathname,
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal title="Abrir ticket" onClose={onCerrar}>
      <ErrorNotice error={error} />
      <Field label="Asunto">
        <input
          className="input"
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          placeholder="En una línea, qué pasa"
        />
      </Field>
      <Field label="Tipo">
        <select className="select" value={tipo} onChange={(e) => setTipo(e.target.value as TipoTicket)}>
          {Object.entries(TIPOS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Prioridad">
        <select
          className="select"
          value={prioridad}
          onChange={(e) => setPrioridad(e.target.value as PrioridadTicket)}
        >
          {Object.entries(PRIORIDADES).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Qué ha pasado">
        <textarea
          className="input"
          rows={7}
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
          placeholder="Qué esperabas, qué ha pasado y desde dónde. Cuanto más concreto, antes se resuelve."
        />
      </Field>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={enviando || !titulo.trim() || !descripcion.trim()}
          onClick={() => void enviar()}
        >
          <Send size={16} aria-hidden="true" /> Abrir ticket
        </button>
      </div>
    </Modal>
  )
}

function DetalleTicket({
  ticket,
  onCerrar,
  onCambio,
  notificar,
}: {
  ticket: Ticket
  onCerrar: () => void
  onCambio: (t: Ticket) => void
  notificar: Notificar
}) {
  const [respuesta, setRespuesta] = useState('')
  const [interno, setInterno] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  // El detalle llega con los mensajes; el listado no. Se recarga al abrir.
  useEffect(() => {
    void (async () => {
      try {
        onCambio(await api.soporte.tickets.get(ticket.id))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Error desconocido')
      }
    })()
    // Solo al cambiar de ticket: `onCambio` cambia en cada render del padre.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticket.id])

  async function responder() {
    setOcupado(true)
    try {
      onCambio(await api.soporte.tickets.responder(ticket.id, respuesta, interno))
      setRespuesta('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  async function cambiarEstado(estado: EstadoTicket) {
    try {
      onCambio(await api.soporte.tickets.update(ticket.id, { estado }))
      notificar(`Ticket ${ESTADOS[estado].toLowerCase()}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title={`${ticket.codigo} · ${ticket.titulo}`} onClose={onCerrar}>
      <ErrorNotice error={error} />

      <div className="form-grid">
        <Field label="Estado">
          <select
            className="select"
            value={ticket.estado}
            onChange={(e) => void cambiarEstado(e.target.value as EstadoTicket)}
          >
            {Object.entries(ESTADOS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Abierto por">
          <input className="input" value={ticket.creado_por_nombre ?? '—'} readOnly />
        </Field>
      </div>

      {ticket.ruta_origen && (
        <p className="muted">Abierto desde <code>{ticket.ruta_origen}</code></p>
      )}

      <section className="card">
        <p style={{ whiteSpace: 'pre-wrap' }}>{ticket.descripcion}</p>
      </section>

      {ticket.mensajes.map((m) => (
        <section key={m.id} className="card">
          <div className="muted">
            {m.creado_por_nombre ?? (m.de_ia ? 'Asistente' : '—')}
            {m.interno && ' · nota interna'}
          </div>
          <p style={{ whiteSpace: 'pre-wrap' }}>{m.cuerpo}</p>
        </section>
      ))}

      <Field label="Responder">
        <textarea
          className="input"
          rows={4}
          value={respuesta}
          onChange={(e) => setRespuesta(e.target.value)}
        />
      </Field>
      <label className="checkbox">
        <input type="checkbox" checked={interno} onChange={(e) => setInterno(e.target.checked)} />
        Nota interna (no la ve quien abrió el ticket)
      </label>

      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={ocupado || !respuesta.trim()}
          onClick={() => void responder()}
        >
          <Send size={16} aria-hidden="true" /> Responder
        </button>
      </div>
    </Modal>
  )
}

// ── Wiki ────────────────────────────────────────────────────────────────

function Wiki({ notificar }: { notificar: Notificar }) {
  const [paginas, setPaginas] = useState<PaginaWiki[]>([])
  const [actual, setActual] = useState<PaginaWiki | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [consulta, setConsulta] = useState('')
  const [resultados, setResultados] = useState<ResultadoBusquedaWiki[] | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setPaginas(await api.soporte.wiki.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const porCategoria = useMemo(() => {
    const mapa = new Map<string, PaginaWiki[]>()
    for (const p of paginas) {
      const clave = p.categoria ?? 'General'
      if (!mapa.has(clave)) mapa.set(clave, [])
      mapa.get(clave)!.push(p)
    }
    return [...mapa.entries()]
  }, [paginas])

  async function buscar() {
    if (!consulta.trim()) {
      setResultados(null)
      return
    }
    setOcupado(true)
    try {
      setResultados(await api.soporte.buscar(consulta))
    } catch (err) {
      // Sin clave de IA no hay embeddings: se dice, no se disimula.
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  async function guardar(pagina: PaginaWiki, nueva: boolean) {
    setOcupado(true)
    try {
      const datos = {
        titulo: pagina.titulo,
        contenido: pagina.contenido,
        categoria: pagina.categoria,
        publicada: pagina.publicada,
      }
      const guardada = nueva
        ? await api.soporte.wiki.create(datos)
        : await api.soporte.wiki.update(pagina.id, datos)
      setActual(null)
      await cargar()
      notificar(
        guardada.indice_al_dia
          ? 'Página guardada e indexada'
          : 'Página guardada (no se ha podido indexar: revisa la clave de IA)',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  async function borrar(pagina: PaginaWiki) {
    if (!window.confirm(`¿Borrar «${pagina.titulo}»?`)) return
    try {
      await api.soporte.wiki.remove(pagina.id)
      setActual(null)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function reindexar() {
    setOcupado(true)
    try {
      const r = await api.soporte.wiki.reindexar()
      notificar(`${r.paginas} páginas · ${r.fragmentos} fragmentos indexados`)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  const vacia: PaginaWiki = {
    id: '',
    slug: '',
    titulo: '',
    contenido: '',
    categoria: null,
    publicada: true,
    version: 1,
    indexada_en: null,
    updated_at: '',
    indice_al_dia: true,
  }

  return (
    <>
      <div className="toolbar" style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 'var(--sp-2)', flex: 1 }}>
          <input
            className="input"
            value={consulta}
            placeholder="Buscar por significado, no solo por palabras…"
            onChange={(e) => setConsulta(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void buscar()}
          />
          <button type="button" className="btn" disabled={ocupado} onClick={() => void buscar()}>
            <Search size={16} aria-hidden="true" /> Buscar
          </button>
        </div>
        <button type="button" className="btn" disabled={ocupado} onClick={() => void reindexar()}>
          <RefreshCw size={16} aria-hidden="true" /> Reindexar
        </button>
        <button type="button" className="btn btn--primary" onClick={() => setActual(vacia)}>
          <Plus size={16} aria-hidden="true" /> Nueva página
        </button>
      </div>
      <ErrorNotice error={error} />

      {resultados !== null && (
        <section className="card">
          <h2 className="form-section__title">Resultados</h2>
          {resultados.length === 0 ? (
            <p className="muted">Nada que se parezca. Prueba con otras palabras o abre un ticket.</p>
          ) : (
            resultados.map((r) => (
              <div key={`${r.origen_id}-${r.texto.slice(0, 20)}`} className="card">
                <strong>{r.titulo}</strong>
                <p style={{ whiteSpace: 'pre-wrap' }}>{r.texto}</p>
              </div>
            ))
          )}
        </section>
      )}

      {paginas.length === 0 ? (
        <EmptyState title="La wiki está vacía">
          Escribe aquí lo que se pregunta una y otra vez. El asistente responde con lo que ponga.
        </EmptyState>
      ) : (
        porCategoria.map(([categoria, lista]) => (
          <section key={categoria} className="form-section">
            <h2 className="form-section__title">{categoria}</h2>
            <ul className="lista">
              {lista.map((p) => (
                <li key={p.id}>
                  <button type="button" className="btn-enlace" onClick={() => setActual(p)}>
                    {p.titulo}
                  </button>
                  {!p.publicada && <span className="badge">borrador</span>}
                  {!p.indice_al_dia && <span className="badge">sin indexar</span>}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      {actual && (
        <EditorPagina
          pagina={actual}
          onCerrar={() => setActual(null)}
          onGuardar={(p) => void guardar(p, actual.id === '')}
          onBorrar={actual.id ? () => void borrar(actual) : undefined}
          ocupado={ocupado}
        />
      )}
    </>
  )
}

function EditorPagina({
  pagina,
  onCerrar,
  onGuardar,
  onBorrar,
  ocupado,
}: {
  pagina: PaginaWiki
  onCerrar: () => void
  onGuardar: (p: PaginaWiki) => void
  onBorrar?: () => void
  ocupado: boolean
}) {
  const [borrador, setBorrador] = useState(pagina)

  return (
    <Modal title={pagina.id ? pagina.titulo : 'Nueva página'} onClose={onCerrar}>
      <Field label="Título">
        <input
          className="input"
          value={borrador.titulo}
          onChange={(e) => setBorrador({ ...borrador, titulo: e.target.value })}
        />
      </Field>
      <Field label="Categoría">
        <input
          className="input"
          value={borrador.categoria ?? ''}
          placeholder="General"
          onChange={(e) => setBorrador({ ...borrador, categoria: e.target.value || null })}
        />
      </Field>
      <Field label="Contenido">
        <textarea
          className="input"
          rows={16}
          value={borrador.contenido}
          onChange={(e) => setBorrador({ ...borrador, contenido: e.target.value })}
        />
      </Field>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={borrador.publicada}
          onChange={(e) => setBorrador({ ...borrador, publicada: e.target.checked })}
        />
        Publicada (si no, no la ve nadie más ni la usa el asistente)
      </label>

      <div className="form-actions">
        {onBorrar && (
          <button type="button" className="btn btn--sm btn--danger" onClick={onBorrar}>
            <Trash2 size={16} aria-hidden="true" /> Borrar
          </button>
        )}
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={ocupado || !borrador.titulo.trim()}
          onClick={() => onGuardar(borrador)}
        >
          <Save size={16} aria-hidden="true" /> Guardar
        </button>
      </div>
    </Modal>
  )
}
