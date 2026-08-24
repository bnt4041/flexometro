import { useState } from 'react'
import { Check, Sparkles, X } from 'lucide-react'

import { ErrorNotice, Modal } from './ui'
import { api } from '../lib/api'
import type { NaturalezaConcepto, PropuestaIA } from '../lib/api'

interface Mensaje {
  rol: 'user' | 'assistant'
  contenido: string
}

/** Conversación con la IA sobre una ficha del banco de precios (Fase 50) —
 *  hermana de `AyudaIAModal`, no el mismo componente: aquella habla del
 *  contexto de un presupuesto (capítulo/partida) y puede proponer copiar o
 *  crear partidas y capítulos enteros; aquí no hay presupuesto detrás, solo
 *  la ficha sobre la que se abrió la conversación. Dos propuestas posibles:
 *  añadir componentes al descompuesto de ESTA ficha, u organizar el banco
 *  entero en capítulos moviendo fichas ya existentes (por fase, por
 *  naturaleza...) — esta segunda no depende de la ficha de origen, es una
 *  operación sobre todo el banco. */
export function AyudaIAModalBanco({
  conceptoId,
  contexto,
  onCambio,
  onClose,
}: {
  conceptoId: string
  contexto: { codigo?: string | null; resumen: string; unidad?: string | null; precio?: string | null }
  onCambio: () => void
  onClose: () => void
}) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [entrada, setEntrada] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [propuesta, setPropuesta] = useState<PropuestaIA | null>(null)
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
        contexto: { tipo: 'ficha', concepto_id: conceptoId, ...contexto },
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

  async function confirmarComponentes(): Promise<string> {
    if (!propuesta) return ''
    // Mismo camino de escritura que añadir un componente a mano en el
    // panel de descompuesto: un concepto personalizado se da de alta
    // primero (como haría el usuario desde el banco de precios) y luego
    // se añade igual que cualquier otro.
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
      await api.conceptos.addLinea(conceptoId, { hijo_id: hijoId, rendimiento: c.rendimiento })
    }
    return `Hecho: ${propuesta.componentes.length} componente${propuesta.componentes.length === 1 ? '' : 's'} añadido${propuesta.componentes.length === 1 ? '' : 's'} al descompuesto.`
  }

  async function confirmarCapitulosBanco(): Promise<string> {
    if (!propuesta) return ''
    // Un capítulo por llamada, en secuencia: cada uno hace su propio
    // capítulo nuevo y luego mueve sus fichas. Con `naturaleza` se mueven
    // TODAS de una sentencia en el servidor (puede ser miles, no solo la
    // muestra que se ha enseñado); si no, la lista concreta encontrada.
    const hechos: string[] = []
    for (const cap of propuesta.capitulos_banco_propuestos) {
      const nuevo = await api.banco.crearCapitulo({ resumen: cap.resumen })
      if (cap.naturaleza) await api.banco.moverPorNaturaleza(cap.naturaleza, nuevo.id)
      else await api.banco.mover(cap.fichas.map((f) => f.concepto_id), nuevo.id)
      hechos.push(`«${cap.resumen}» (${cap.total_fichas} ficha${cap.total_fichas === 1 ? '' : 's'})`)
    }
    return `Hecho: capítulo${hechos.length === 1 ? '' : 's'} creado${hechos.length === 1 ? '' : 's'} ${hechos.join(', ')}.`
  }

  async function confirmar() {
    if (!propuesta || confirmando) return
    setConfirmando(true)
    setError(null)
    try {
      const texto =
        propuesta.tipo === 'organizar_capitulos_banco'
          ? await confirmarCapitulosBanco()
          : await confirmarComponentes()
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
          Sobre <strong>«{contexto.resumen}»</strong> — puede buscar en todo el banco de precios de
          la cuenta, proponer componentes para el descompuesto de esta ficha, o organizar el banco
          en capítulos moviendo fichas ya existentes.
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

        {propuesta && propuesta.tipo === 'anadir_componentes_ficha' && (
          <div className="chat-ia__propuesta">
            <p>{propuesta.descripcion}</p>
            <ul className="chat-ia__componentes">
              {propuesta.componentes.map((c, i) => (
                <li key={c.concepto_id ?? i}>
                  {c.rendimiento} {c.unidad} —{' '}
                  {c.personalizado ? (
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
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <button className="btn btn--sm" disabled={confirmando} onClick={() => void confirmar()}>
                <Check size={14} aria-hidden="true" />
                Confirmar y añadir
              </button>
              <button className="btn btn--sm" disabled={confirmando} onClick={() => setPropuesta(null)}>
                <X size={14} aria-hidden="true" />
                Descartar
              </button>
            </div>
          </div>
        )}

        {propuesta && propuesta.tipo === 'organizar_capitulos_banco' && (
          <div className="chat-ia__propuesta">
            <p>{propuesta.descripcion}</p>
            <div className="chat-ia__capitulos">
              {propuesta.capitulos_banco_propuestos.map((cap, k) => (
                <div key={k} className="chat-ia__capitulo">
                  <strong>
                    {cap.resumen} <span className="muted">({cap.total_fichas} ficha{cap.total_fichas === 1 ? '' : 's'})</span>
                  </strong>
                  <ul className="chat-ia__componentes">
                    {cap.fichas.map((f) => (
                      <li key={f.concepto_id}>
                        {f.codigo} · {f.resumen}
                      </li>
                    ))}
                  </ul>
                  {cap.total_fichas > cap.fichas.length && (
                    <p className="muted" style={{ margin: 0 }}>
                      … y {cap.total_fichas - cap.fichas.length} más (se moverán todas al confirmar)
                    </p>
                  )}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <button className="btn btn--sm" disabled={confirmando} onClick={() => void confirmar()}>
                <Check size={14} aria-hidden="true" />
                {propuesta.capitulos_banco_propuestos.length === 1
                  ? 'Confirmar y crear capítulo'
                  : `Confirmar los ${propuesta.capitulos_banco_propuestos.length} capítulos`}
              </button>
              <button className="btn btn--sm" disabled={confirmando} onClick={() => setPropuesta(null)}>
                <X size={14} aria-hidden="true" />
                Descartar
              </button>
            </div>
          </div>
        )}

        <ErrorNotice error={error} />

        <label className="field">
          <span className="field__label">Mensaje</span>
          <textarea
            className="input"
            rows={2}
            placeholder="¿Qué componentes quieres añadir a esta ficha?"
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
