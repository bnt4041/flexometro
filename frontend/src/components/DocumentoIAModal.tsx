import { useEffect, useRef, useState } from 'react'
import { Check, FileSpreadsheet, FileText, Image as ImageIcon, Plus, Save, Sparkles, X } from 'lucide-react'

import { ErrorNotice, ModalPantalla } from './ui'
import { api } from '../lib/api'
import type { EntidadDocumento, PropuestaIA } from '../lib/api'

interface Mensaje {
  rol: 'user' | 'assistant'
  contenido: string
}

const PRIMER_MENSAJE = '¿Qué tipo de documento es este y qué contiene?'
const EXTENSIONES_ADMITIDAS = '.pdf,.xlsx,image/png,image/jpeg,image/webp,application/pdf'

function tipoDe(fichero: File): 'imagen' | 'pdf' | 'excel' | 'otro' {
  const nombre = fichero.name.toLowerCase()
  if (fichero.type.startsWith('image/')) return 'imagen'
  if (fichero.type === 'application/pdf' || nombre.endsWith('.pdf')) return 'pdf'
  if (nombre.endsWith('.xlsx')) return 'excel'
  return 'otro'
}

/** Documento o documentos (PDF, imagen, Excel) arrastrados a una fila del
 *  presupuesto — "Arrastrar al presupuesto" (Fase 41). Un visor a un lado
 *  para poder cotejar lo que dice la IA contra el documento real —con
 *  pestañas si hay más de uno—, y al otro una conversación libre: al
 *  abrirse, se manda sola una primera pregunta para que la IA identifique
 *  qué es sin que haga falta pedírselo. Se pueden añadir más documentos a
 *  media conversación con el botón "+"; guardarlos en Documentos es un botón
 *  aparte, no algo que dispare la conversación.
 *
 *  Si se sabe sobre qué presupuesto se abrió (`presupuestoId`), la IA puede
 *  además terminar proponiendo un capítulo nuevo con lo que lea de los
 *  documentos — igual que "Ayuda con IA", nunca lo crea ella sola: la
 *  propuesta se enseña como tarjeta aparte y hay que confirmarla. */
export function DocumentoIAModal({
  ficheros: ficherosIniciales,
  entidad,
  entidadId,
  presupuestoId,
  onClose,
  onGuardado,
  onCambio,
}: {
  ficheros: File[]
  entidad: EntidadDocumento
  entidadId: string
  presupuestoId?: string
  onClose: () => void
  onGuardado?: () => void
  onCambio?: () => void
}) {
  const [ficheros, setFicheros] = useState<File[]>(ficherosIniciales)
  const [activo, setActivo] = useState(0)
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [entrada, setEntrada] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [guardado, setGuardado] = useState(false)
  const [propuesta, setPropuesta] = useState<PropuestaIA | null>(null)
  const [confirmando, setConfirmando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [urls, setUrls] = useState<(string | null)[]>([])
  const [tablasExcel, setTablasExcel] = useState<Record<number, string>>({})
  const inputAnadirRef = useRef<HTMLInputElement>(null)

  // Un blob por fichero (imagen/PDF), creado y revocado en el mismo efecto:
  // si se crea aparte (p. ej. en un `useMemo`) y solo se revoca en la
  // limpieza, el doble montaje de StrictMode revoca sin volver a crear y la
  // vista previa se queda apuntando a una URL ya muerta.
  useEffect(() => {
    const nuevas = ficheros.map((f) => {
      const tipo = tipoDe(f)
      return tipo === 'imagen' || tipo === 'pdf' ? URL.createObjectURL(f) : null
    })
    setUrls(nuevas)
    return () => {
      for (const u of nuevas) if (u) URL.revokeObjectURL(u)
    }
  }, [ficheros])

  // La tabla de un Excel se trae aparte (sin pasar por la IA) solo para
  // enseñarla en el visor — la misma que ve Gemini, pero al instante.
  useEffect(() => {
    let cancelado = false
    ficheros.forEach((f, i) => {
      if (tipoDe(f) !== 'excel' || tablasExcel[i] !== undefined) return
      api.ia
        .previsualizarExcel(f)
        .then(({ tabla }) => {
          if (!cancelado) setTablasExcel((actual) => ({ ...actual, [i]: tabla }))
        })
        .catch(() => {
          if (!cancelado) setTablasExcel((actual) => ({ ...actual, [i]: '' }))
        })
    })
    return () => {
      cancelado = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ficheros])

  async function enviarMensaje(
    contenido: string,
    historialPrevio: Mensaje[],
    // `ficheros` del estado puede no reflejar todavía un fichero recién
    // añadido (`setFicheros` no es síncrono) — quien acaba de añadirlo pasa
    // la lista ya combinada para no mandar la conversación sin él.
    ficherosActuales: File[] = ficheros,
  ) {
    setError(null)
    setPropuesta(null)
    const historial = [...historialPrevio, { rol: 'user' as const, contenido }]
    setMensajes(historial)
    setEnviando(true)
    try {
      const { respuesta, propuesta: nueva } = await api.ia.documentoConversar(
        ficherosActuales,
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

  function anadirFicheros(nuevos: File[]) {
    if (nuevos.length === 0) return
    const combinados = [...ficheros, ...nuevos]
    setFicheros(combinados)
    setActivo(ficheros.length) // salta al primero de los recién añadidos
    setGuardado(false)
    const nombres = nuevos.map((f) => f.name).join(', ')
    void enviarMensaje(
      nuevos.length === 1
        ? `He añadido otro documento: ${nombres}. ¿Qué es y qué contiene?`
        : `He añadido más documentos: ${nombres}. ¿Qué son y qué contienen?`,
      mensajes,
      combinados,
    )
  }

  async function guardarEnDocumentos() {
    if (guardando) return
    setGuardando(true)
    setError(null)
    try {
      for (const fichero of ficheros) {
        await api.documentos.upload(entidad, entidadId, fichero)
      }
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

  const ficheroActivo = ficheros[activo]
  const tipoActivo = ficheroActivo ? tipoDe(ficheroActivo) : 'otro'
  const iconoDe = (tipo: ReturnType<typeof tipoDe>) =>
    tipo === 'excel' ? (
      <FileSpreadsheet size={13} aria-hidden="true" />
    ) : tipo === 'imagen' ? (
      <ImageIcon size={13} aria-hidden="true" />
    ) : (
      <FileText size={13} aria-hidden="true" />
    )

  return (
    <ModalPantalla
      title={
        ficheros.length === 1
          ? `Documento — ${ficheros[0].name}`
          : `Documentos — ${ficheros.length} ficheros`
      }
      onClose={onClose}
    >
      <div className="documento-ia">
        <div className="documento-ia__panel">
          {ficheros.length > 1 && (
            <div className="documento-ia__pestanas">
              {ficheros.map((f, i) => (
                <button
                  key={i}
                  type="button"
                  className={
                    i === activo
                      ? 'documento-ia__pestana is-activa'
                      : 'documento-ia__pestana'
                  }
                  onClick={() => setActivo(i)}
                  title={f.name}
                >
                  {iconoDe(tipoDe(f))}
                  <span>{f.name}</span>
                </button>
              ))}
            </div>
          )}
          <div className="documento-ia__visor">
            {tipoActivo === 'imagen' && urls[activo] ? (
              <img src={urls[activo]!} alt={ficheroActivo.name} />
            ) : tipoActivo === 'pdf' && urls[activo] ? (
              <iframe src={urls[activo]!} title={ficheroActivo.name} />
            ) : tipoActivo === 'excel' ? (
              tablasExcel[activo] === undefined ? (
                <div className="documento-ia__sin-visor">
                  <FileSpreadsheet size={40} aria-hidden="true" />
                  <p className="muted">Leyendo el Excel…</p>
                </div>
              ) : tablasExcel[activo] === '' ? (
                <div className="documento-ia__sin-visor">
                  <FileSpreadsheet size={40} aria-hidden="true" />
                  <p>{ficheroActivo.name}</p>
                  <p className="muted">No se ha podido leer el contenido.</p>
                </div>
              ) : (
                <pre className="documento-ia__tabla-excel">{tablasExcel[activo]}</pre>
              )
            ) : (
              <div className="documento-ia__sin-visor">
                <FileText size={40} aria-hidden="true" />
                <p>{ficheroActivo?.name}</p>
                <p className="muted">No hay vista previa para este tipo de fichero.</p>
              </div>
            )}
          </div>
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
              placeholder="¿Qué quieres saber o hacer con estos documentos?"
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
              disabled={enviando}
              onClick={() => inputAnadirRef.current?.click()}
              title="Añadir otro documento a esta conversación"
            >
              <Plus size={16} aria-hidden="true" />
              Añadir documento
            </button>
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
      <input
        ref={inputAnadirRef}
        type="file"
        multiple
        accept={EXTENSIONES_ADMITIDAS}
        style={{ display: 'none' }}
        onChange={(e) => {
          const nuevos = Array.from(e.target.files ?? [])
          e.target.value = ''
          anadirFicheros(nuevos)
        }}
      />
    </ModalPantalla>
  )
}
