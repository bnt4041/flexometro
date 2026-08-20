import { useEffect, useMemo, useState } from 'react'
import { Check, FileSpreadsheet, Save, Sparkles, X } from 'lucide-react'

import { ErrorNotice, ModalPantalla } from './ui'
import { api } from '../lib/api'
import type { EntidadDocumento, PropuestaIA } from '../lib/api'

interface Mensaje {
  rol: 'user' | 'assistant'
  contenido: string
}

const PRIMER_MENSAJE = '¿Qué tipo de documento es este y qué contiene?'

/** Documento (PDF, imagen o Excel) arrastrado a una fila del presupuesto —
 *  "Arrastrar al presupuesto". Un visor a un lado para poder cotejar lo que
 *  dice la IA contra el documento real, y al otro una conversación libre:
 *  al abrirse, se manda sola una primera pregunta para que la IA identifique
 *  qué es sin que haga falta pedírselo. Guardarlo en Documentos es un botón
 *  aparte, no algo que dispare la conversación.
 *
 *  Si se sabe sobre qué presupuesto se abrió (`presupuestoId`), la IA puede
 *  además terminar proponiendo un capítulo nuevo con lo que lea del
 *  documento — igual que "Ayuda con IA", nunca lo crea ella sola: la
 *  propuesta se enseña como tarjeta aparte y hay que confirmarla. */
export function DocumentoIAModal({
  fichero,
  entidad,
  entidadId,
  presupuestoId,
  onClose,
  onGuardado,
  onCambio,
}: {
  fichero: File
  entidad: EntidadDocumento
  entidadId: string
  presupuestoId?: string
  onClose: () => void
  onGuardado?: () => void
  onCambio?: () => void
}) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [entrada, setEntrada] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [guardado, setGuardado] = useState(false)
  const [propuesta, setPropuesta] = useState<PropuestaIA | null>(null)
  const [confirmando, setConfirmando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const esImagen = fichero.type.startsWith('image/')
  const esPdf = fichero.type === 'application/pdf' || fichero.name.toLowerCase().endsWith('.pdf')
  const url = useMemo(
    () => (esImagen || esPdf ? URL.createObjectURL(fichero) : null),
    [fichero, esImagen, esPdf],
  )
  useEffect(() => () => { if (url) URL.revokeObjectURL(url) }, [url])

  async function enviarMensaje(contenido: string, historialPrevio: Mensaje[]) {
    setError(null)
    setPropuesta(null)
    const historial = [...historialPrevio, { rol: 'user' as const, contenido }]
    setMensajes(historial)
    setEnviando(true)
    try {
      const { respuesta, propuesta: nueva } = await api.ia.documentoConversar(
        fichero,
        historial.map((m) => ({ rol: m.rol, contenido: m.contenido })),
        presupuestoId,
      )
      setMensajes((actual) => [...actual, { rol: 'assistant', contenido: respuesta }])
      if (nueva) setPropuesta(nueva)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  // Se dispara sola en cuanto se abre, para que la IA diga qué es el
  // documento sin que el usuario tenga que preguntarlo primero.
  useEffect(() => {
    void enviarMensaje(PRIMER_MENSAJE, [])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function enviar() {
    const texto = entrada.trim()
    if (texto === '' || enviando) return
    setEntrada('')
    await enviarMensaje(texto, mensajes)
  }

  async function guardarEnDocumentos() {
    if (guardando) return
    setGuardando(true)
    setError(null)
    try {
      await api.documentos.upload(entidad, entidadId, fichero)
      setGuardado(true)
      onGuardado?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function confirmarPropuesta() {
    if (!propuesta || !presupuestoId || confirmando) return
    setConfirmando(true)
    setError(null)
    try {
      const capitulo = await api.presupuestos.addCapitulo(presupuestoId, {
        resumen: propuesta.capitulo_resumen || 'Importado de documento',
      })
      for (const p of propuesta.partidas_propuestas) {
        await api.capitulos.addPartida(capitulo.id, {
          resumen: p.resumen,
          unidad: p.unidad,
          precio: p.precio,
          lineas: [{ uds: p.medicion }],
        })
      }
      setPropuesta(null)
      setMensajes((actual) => [
        ...actual,
        {
          rol: 'assistant',
          contenido: `Hecho: capítulo «${capitulo.resumen}» creado con ${propuesta.partidas_propuestas.length} partida${propuesta.partidas_propuestas.length === 1 ? '' : 's'}.`,
        },
      ])
      onCambio?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setConfirmando(false)
    }
  }

  return (
    <ModalPantalla title={`Documento — ${fichero.name}`} onClose={onClose}>
      <div className="documento-ia">
        <div className="documento-ia__visor">
          {esImagen && url ? (
            <img src={url} alt={fichero.name} />
          ) : esPdf && url ? (
            <iframe src={url} title={fichero.name} />
          ) : (
            <div className="documento-ia__sin-visor">
              <FileSpreadsheet size={40} aria-hidden="true" />
              <p>{fichero.name}</p>
              <p className="muted">No hay vista previa para este tipo de fichero.</p>
            </div>
          )}
        </div>
        <div className="documento-ia__chat">
          <div className="chat-ia">
            {mensajes.map((m, i) => (
              <div key={i} className={m.rol === 'user' ? 'chat-ia__burbuja is-usuario' : 'chat-ia__burbuja'}>
                {m.contenido}
              </div>
            ))}
            {enviando && <div className="chat-ia__burbuja muted">Consultando a Gemini…</div>}
          </div>

          {propuesta && (
            <div className="chat-ia__propuesta">
              <p>{propuesta.descripcion}</p>
              {propuesta.partidas_propuestas.length > 0 && (
                <ul className="chat-ia__componentes">
                  {propuesta.partidas_propuestas.map((p, i) => (
                    <li key={i}>
                      {p.resumen} — {p.medicion} {p.unidad} × {p.precio} €
                    </li>
                  ))}
                </ul>
              )}
              {presupuestoId ? (
                <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                  <button
                    className="btn btn--sm"
                    disabled={confirmando}
                    onClick={() => void confirmarPropuesta()}
                  >
                    <Check size={14} aria-hidden="true" />
                    Confirmar y crear aquí
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
                  Abre este documento desde un presupuesto para poder confirmarlo.
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
              placeholder="¿Qué quieres saber o hacer con este documento?"
              value={entrada}
              onChange={(e) => setEntrada(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void enviar()
                }
              }}
            />
          </label>

          <div className="form-actions">
            <button
              className="btn"
              disabled={guardando || guardado}
              onClick={() => void guardarEnDocumentos()}
            >
              <Save size={16} aria-hidden="true" />
              {guardado ? 'Guardado' : guardando ? 'Guardando…' : 'Guardar en Documentos'}
            </button>
            <button
              className="btn btn--primary"
              disabled={enviando || entrada.trim() === ''}
              onClick={() => void enviar()}
            >
              {!enviando && <Sparkles size={16} aria-hidden="true" />}
              {enviando ? 'Consultando a Gemini…' : 'Enviar'}
            </button>
          </div>
        </div>
      </div>
    </ModalPantalla>
  )
}
