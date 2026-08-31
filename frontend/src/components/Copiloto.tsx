import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Check, MessageCircle, Send, Sparkles, X } from 'lucide-react'

import { api } from '../lib/api'
import type { MensajeCopiloto, PropuestaCopiloto } from '../lib/api'
import { useToast } from '../toast'
import { useWorkspace } from '../workspace'

const SUGERENCIAS = [
  '¿Cuánto he facturado este año y a quién?',
  '¿Cómo doy de alta un proveedor?',
  '¿Qué obras tengo en marcha?',
]

/** El copiloto: un chat que acompaña a toda la aplicación.
 *
 *  Lo que hace distinto a este chat de un buscador es que puede llegar a
 *  proponer una escritura. Nunca la ejecuta: la propuesta se pinta con sus
 *  campos a la vista y hace falta pulsar "Confirmar" — y al confirmar, el
 *  servidor vuelve a comprobar el permiso desde cero. Un modelo que se
 *  equivoca de cliente produce aquí una pregunta, no un registro. */
export function Copiloto() {
  const { modules } = useWorkspace()
  const { notificar } = useToast()
  const location = useLocation()
  const navigate = useNavigate()

  const [abierto, setAbierto] = useState(false)
  const [mensajes, setMensajes] = useState<MensajeCopiloto[]>([])
  const [borrador, setBorrador] = useState('')
  const [propuesta, setPropuesta] = useState<PropuestaCopiloto | null>(null)
  const [pensando, setPensando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const finRef = useRef<HTMLDivElement>(null)

  // Sin el módulo de IA activo no hay a quién preguntar: mejor no enseñar un
  // botón que solo puede dar un error.
  const disponible = modules.some((m) => m.code === 'ia' && m.is_active)

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [mensajes, propuesta, pensando])

  if (!disponible) return null

  async function preguntar(texto: string) {
    const limpio = texto.trim()
    if (!limpio || pensando) return
    // Se manda el historial completo, incluido el mensaje nuevo: el estado de
    // React todavía no lo tiene cuando llega aquí.
    const historial = [...mensajes, { rol: 'user' as const, contenido: limpio }]
    setMensajes(historial)
    setBorrador('')
    setPropuesta(null)
    setError(null)
    setPensando(true)
    try {
      const r = await api.copiloto.conversar(historial, location.pathname)
      setMensajes([...historial, { rol: 'assistant', contenido: r.respuesta }])
      setPropuesta(r.propuesta)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setPensando(false)
    }
  }

  async function confirmar() {
    if (!propuesta) return
    setPensando(true)
    try {
      const hecho = await api.copiloto.confirmar(propuesta)
      setPropuesta(null)
      setMensajes((prev) => [...prev, { rol: 'assistant', contenido: `✓ ${hecho.descripcion}` }])
      notificar(hecho.descripcion)
      if (hecho.ruta) navigate(hecho.ruta)
    } catch (err) {
      const motivo = err instanceof Error ? err.message : 'Error desconocido'
      setError(motivo)
      // El fallo entra en el hilo, no solo en el banner: si no, el copiloto
      // sigue creyendo que aquello salió bien y en el siguiente turno da por
      // hecho un registro que no existe. Casi siempre es la validación real
      // del módulo dueño (un NIF que no cuadra), y con el motivo delante
      // puede corregir y volver a proponer.
      setMensajes((prev) => [
        ...prev,
        { rol: 'assistant', contenido: `No se ha podido aplicar: ${motivo}` },
      ])
    } finally {
      setPensando(false)
    }
  }

  if (!abierto) {
    return (
      <button
        type="button"
        className="copiloto__lanzador"
        aria-label="Abrir el copiloto"
        onClick={() => setAbierto(true)}
      >
        <MessageCircle size={20} aria-hidden="true" />
      </button>
    )
  }

  return (
    <aside className="copiloto" role="complementary" aria-label="Copiloto">
      <header className="copiloto__cabecera">
        <Sparkles size={16} aria-hidden="true" />
        <span className="copiloto__titulo">Copiloto</span>
        <button
          type="button"
          className="copiloto__cerrar"
          aria-label="Cerrar"
          onClick={() => setAbierto(false)}
        >
          <X size={16} aria-hidden="true" />
        </button>
      </header>

      <div className="copiloto__hilo">
        {mensajes.length === 0 && (
          <div className="copiloto__bienvenida">
            <p>
              Pregúntame por tus datos, por cómo se hace algo, o pídeme que cree
              algo. Lo que haya que escribir te lo enseño antes y decides tú.
            </p>
            {SUGERENCIAS.map((s) => (
              <button
                key={s}
                type="button"
                className="copiloto__sugerencia"
                onClick={() => void preguntar(s)}
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {mensajes.map((m, i) => (
          <div
            key={i}
            className={m.rol === 'user' ? 'copiloto__msg copiloto__msg--mio' : 'copiloto__msg'}
          >
            {m.contenido}
          </div>
        ))}

        {pensando && <div className="copiloto__msg copiloto__msg--pensando">Pensando…</div>}

        {propuesta && (
          <div className="copiloto__propuesta">
            <strong>{propuesta.resumen}</strong>
            <dl className="copiloto__campos">
              {propuesta.campos.map((c) => (
                <div key={c.etiqueta}>
                  <dt>{c.etiqueta}</dt>
                  <dd>{c.valor}</dd>
                </div>
              ))}
            </dl>
            <p className="copiloto__aviso">Todavía no se ha hecho nada.</p>
            <div className="copiloto__acciones">
              <button type="button" className="btn btn--sm" onClick={() => setPropuesta(null)}>
                Descartar
              </button>
              <button
                type="button"
                className="btn btn--sm btn--primary"
                disabled={pensando}
                onClick={() => void confirmar()}
              >
                <Check size={14} aria-hidden="true" /> Confirmar
              </button>
            </div>
          </div>
        )}

        {error && <div className="copiloto__error">{error}</div>}
        <div ref={finRef} />
      </div>

      <form
        className="copiloto__pie"
        onSubmit={(e) => {
          e.preventDefault()
          void preguntar(borrador)
        }}
      >
        <input
          className="input"
          value={borrador}
          placeholder="Escribe tu pregunta…"
          onChange={(e) => setBorrador(e.target.value)}
        />
        <button
          type="submit"
          className="btn btn--primary btn--sm"
          aria-label="Enviar"
          disabled={pensando || !borrador.trim()}
        >
          <Send size={14} aria-hidden="true" />
        </button>
      </form>
    </aside>
  )
}
