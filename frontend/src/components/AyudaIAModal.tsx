import { useState } from 'react'
import { Check, Sparkles, X } from 'lucide-react'

import { ErrorNotice, Modal } from './ui'
import { api } from '../lib/api'
import type { AlcancePegado, NaturalezaConcepto, PropuestaIA } from '../lib/api'

interface Mensaje {
  rol: 'user' | 'assistant'
  contenido: string
}

type Propuesta = PropuestaIA

/** Conversación con la IA sobre una línea del presupuesto (Fase 1g/1h). Tiene
 *  acceso de solo lectura a toda la cuenta (presupuestos, partidas, banco de
 *  precios) y puede terminar proponiendo una acción — copiar una partida ya
 *  existente, o montar una nueva con componentes del banco — pero nunca la
 *  ejecuta ella sola: la propuesta se enseña como una tarjeta aparte que hay
 *  que confirmar, y esa confirmación reutiliza los mismos endpoints que ya
 *  usan Ctrl+V/arrastrar y el botón "+ Línea" del descompuesto, no un camino
 *  de escritura nuevo. */
export function AyudaIAModal({
  contexto,
  destinoCapituloId,
  onCambio,
  onClose,
}: {
  contexto: {
    tipo: 'capitulo' | 'partida'
    codigo?: string | null
    resumen: string
    unidad?: string | null
    precio?: string | null
    presupuesto_id: string
    presupuesto_nombre: string
  }
  /** Capítulo donde iría una partida propuesta (copiada o nueva) si se
   *  confirma — el de la fila desde la que se abrió esta conversación. */
  destinoCapituloId: string | null
  onCambio: () => void
  onClose: () => void
}) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [entrada, setEntrada] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [propuesta, setPropuesta] = useState<Propuesta | null>(null)
  const [confirmando, setConfirmando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function enviar() {
    const texto = entrada.trim()
    if (texto === '' || enviando) return
    setError(null)
    setPropuesta(null)
    const historial = [...mensajes, { rol: 'user' as const, contenido: texto }]
    setMensajes(historial)
    setEntrada('')
    setEnviando(true)
    try {
      const { respuesta, propuesta: nueva } = await api.ia.ayudaLineaConversar({
        contexto,
        mensajes: historial.map((m) => ({ rol: m.rol, contenido: m.contenido })),
      })
      setMensajes((actual) => [...actual, { rol: 'assistant', contenido: respuesta }])
      if (nueva) setPropuesta(nueva)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  async function confirmarCopiar(alcance: AlcancePegado) {
    if (!propuesta?.partida_id || !destinoCapituloId) return
    const resultado = await api.capitulos.pegarPartidas(destinoCapituloId, {
      partida_ids: [propuesta.partida_id],
      alcance,
    })
    return resultado.pegadas === 1
      ? 'Hecho: partida copiada aquí.'
      : 'No se ha podido copiar (puede que ya no exista o no sea de esta cuenta).'
  }

  async function confirmarCrear() {
    if (!propuesta?.resumen || !propuesta.unidad || !destinoCapituloId) return
    // La misma partida en dos pasos: se crea vacía (como el botón "+
    // Partida") y luego se le añaden sus componentes uno a uno (como el "+
    // Línea" del descompuesto) — nada que no se pudiera hacer ya a mano. Un
    // componente personalizado necesita un paso previo: darlo de alta en el
    // banco de precios (como haría el usuario a mano desde esa pantalla)
    // antes de poder añadirlo igual que cualquier otro.
    const nueva = await api.capitulos.addPartida(destinoCapituloId, {
      resumen: propuesta.resumen,
      unidad: propuesta.unidad,
      precio: '0',
    })
    for (const c of propuesta.componentes) {
      const hijoId = c.personalizado
        ? (
            await api.conceptos.create({
              tipo: 'basico',
              naturaleza: (c.naturaleza as NaturalezaConcepto) ?? 'sin_clasificar',
              unidad: c.unidad,
              resumen: c.resumen,
              precio: c.precio ?? '0',
              origen_precio: 'manual',
              origen_dato: 'ia',
            })
          ).id
        : c.concepto_id!
      await api.partidas.anadirComponente(nueva.id, {
        hijo_id: hijoId,
        rendimiento: c.rendimiento,
      })
    }
    return `Hecho: partida «${propuesta.resumen}» creada con ${propuesta.componentes.length} componente${propuesta.componentes.length === 1 ? '' : 's'}.`
  }

  async function confirmarPropuesta(alcance: AlcancePegado) {
    if (!propuesta || confirmando) return
    setConfirmando(true)
    setError(null)
    try {
      const texto =
        propuesta.tipo === 'copiar_partida' ? await confirmarCopiar(alcance) : await confirmarCrear()
      setPropuesta(null)
      if (texto) setMensajes((actual) => [...actual, { rol: 'assistant', contenido: texto }])
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setConfirmando(false)
    }
  }

  return (
    <Modal title="Ayuda con IA" onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          Sobre <strong>«{contexto.resumen}»</strong> — puede buscar en cualquier presupuesto o el
          banco de precios de la cuenta.
        </p>

        {mensajes.length > 0 && (
          <div className="chat-ia">
            {mensajes.map((m, i) => (
              <div key={i} className={m.rol === 'user' ? 'chat-ia__burbuja is-usuario' : 'chat-ia__burbuja'}>
                {m.contenido}
              </div>
            ))}
            {enviando && <div className="chat-ia__burbuja muted">Consultando a DeepSeek…</div>}
          </div>
        )}

        {propuesta && (
          <div className="chat-ia__propuesta">
            <p>{propuesta.descripcion}</p>
            {propuesta.tipo === 'crear_partida' && propuesta.componentes.length > 0 && (
              <ul className="chat-ia__componentes">
                {propuesta.componentes.map((c, i) => (
                  <li key={c.concepto_id ?? i}>
                    {c.rendimiento} {c.unidad} — {c.personalizado ? (
                      <>
                        {c.resumen} · <strong>personalizado, {c.precio} €</strong>
                      </>
                    ) : (
                      <>
                        {c.codigo} · {c.resumen}
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {destinoCapituloId ? (
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                <button
                  className="btn btn--sm"
                  disabled={confirmando}
                  onClick={() => void confirmarPropuesta('copiar')}
                >
                  <Check size={14} aria-hidden="true" />
                  {propuesta.tipo === 'copiar_partida' ? 'Confirmar y copiar aquí' : 'Confirmar y crear aquí'}
                </button>
                <button
                  className="btn btn--sm"
                  disabled={confirmando}
                  onClick={() => setPropuesta(null)}
                >
                  <X size={14} aria-hidden="true" />
                  Descartar
                </button>
              </div>
            ) : (
              <p className="muted">
                No hay un capítulo de destino claro aquí — abre esta ayuda desde una partida o un
                capítulo del presupuesto para poder confirmarlo.
              </p>
            )}
          </div>
        )}

        <ErrorNotice error={error} />

        <label className="field">
          <span className="field__label">Mensaje</span>
          <textarea
            className="input"
            rows={2}
            placeholder="¿Qué quieres saber o buscar?"
            value={entrada}
            onChange={(e) => setEntrada(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void enviar()
              }
            }}
            autoFocus
          />
        </label>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cerrar
        </button>
        <button className="btn btn--primary" disabled={enviando || entrada.trim() === ''} onClick={() => void enviar()}>
          {!enviando && <Sparkles size={16} aria-hidden="true" />}
          {enviando ? 'Consultando a DeepSeek…' : 'Enviar'}
        </button>
      </div>
    </Modal>
  )
}
