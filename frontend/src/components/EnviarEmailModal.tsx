import { useEffect, useRef, useState } from 'react'
import { Paperclip, Send, Upload, X } from 'lucide-react'

import { EditorHtml } from './EditorHtml'
import { Checkbox, ErrorNotice, Field, Modal } from './ui'
import { api } from '../lib/api'
import type { Documento, DocumentoBusqueda, EntidadNota } from '../lib/api'

function formatoTamano(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const ETIQUETA_ENTIDAD: Record<string, string> = {
  tercero: 'Terceros',
  presupuesto: 'Presupuestos',
  obra: 'Obras',
  certificacion: 'Certificaciones',
  factura: 'Facturas',
}

type AdjuntoElegido = { id: string; nombre_archivo: string }

/** Enviar un correo desde la pestaña CRM de cualquier ficha (Fase 42): se
 *  registra como una nota más al terminar. Los adjuntos se eligen primero
 *  entre los documentos ya subidos a ESTA ficha; si no está el que hace
 *  falta, un buscador por nombre encuentra cualquier documento de la cuenta,
 *  agrupado por de qué módulo viene. */
export function EnviarEmailModal({
  entidad,
  entidadId,
  destinatarioSugerido,
  onClose,
  onEnviado,
}: {
  entidad: EntidadNota
  entidadId: string
  destinatarioSugerido?: string
  onClose: () => void
  onEnviado: () => void
}) {
  const [destinatario, setDestinatario] = useState(destinatarioSugerido ?? '')
  const [asunto, setAsunto] = useState('')
  const [cuerpo, setCuerpo] = useState('')
  const [elegidos, setElegidos] = useState<AdjuntoElegido[]>([])
  const [documentosFicha, setDocumentosFicha] = useState<Documento[]>([])
  const [busqueda, setBusqueda] = useState('')
  const [resultados, setResultados] = useState<DocumentoBusqueda[]>([])
  const [buscando, setBuscando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const temporizador = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [nuevosArchivos, setNuevosArchivos] = useState<File[]>([])
  const [guardarEnFicha, setGuardarEnFicha] = useState(true)
  const [arrastrando, setArrastrando] = useState(false)
  const inputArchivoRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    void api.documentos.list(entidad, entidadId).then(setDocumentosFicha).catch(() => setDocumentosFicha([]))
  }, [entidad, entidadId])

  useEffect(() => {
    if (busqueda.trim().length < 2) {
      setResultados([])
      return
    }
    setBuscando(true)
    if (temporizador.current) clearTimeout(temporizador.current)
    temporizador.current = setTimeout(() => {
      void api.documentos
        .buscar(busqueda.trim())
        .then(setResultados)
        .catch(() => setResultados([]))
        .finally(() => setBuscando(false))
    }, 350)
    return () => {
      if (temporizador.current) clearTimeout(temporizador.current)
    }
  }, [busqueda])

  function alternar(documento: { id: string; nombre_archivo: string }) {
    setElegidos((actual) =>
      actual.some((d) => d.id === documento.id)
        ? actual.filter((d) => d.id !== documento.id)
        : [...actual, { id: documento.id, nombre_archivo: documento.nombre_archivo }],
    )
  }

  const resultadosPorEntidad = resultados.reduce<Record<string, DocumentoBusqueda[]>>((acc, d) => {
    ;(acc[d.entidad] ??= []).push(d)
    return acc
  }, {})

  function anadirArchivos(lista: FileList | null) {
    if (!lista) return
    setNuevosArchivos((actual) => [...actual, ...Array.from(lista)])
  }

  function quitarArchivo(indice: number) {
    setNuevosArchivos((actual) => actual.filter((_, i) => i !== indice))
  }

  async function enviar() {
    if (!destinatario.trim() || !asunto.trim() || !cuerpo.trim()) {
      setError('Destinatario, asunto y cuerpo son obligatorios')
      return
    }
    setEnviando(true)
    setError(null)
    try {
      await api.notas.enviarEmail(entidad, entidadId, {
        destinatario: destinatario.trim(),
        asunto: asunto.trim(),
        cuerpo_html: cuerpo,
        documento_ids: elegidos.map((d) => d.id),
        guardar_adjuntos: guardarEnFicha,
        archivos: nuevosArchivos,
      })
      onEnviado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <Modal title="Enviar correo" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field ancho="doble" label="Para">
            <input
              className="input"
              type="email"
              value={destinatario}
              onChange={(e) => setDestinatario(e.target.value)}
              placeholder="cliente@ejemplo.com"
              autoFocus
            />
          </Field>
          <Field ancho="doble" label="Asunto">
            <input className="input" value={asunto} onChange={(e) => setAsunto(e.target.value)} />
          </Field>
        </div>

        <Field label="Mensaje">
          <div style={{ height: 220 }}>
            <EditorHtml value={cuerpo} onChange={setCuerpo} placeholder="Escribe el correo…" />
          </div>
        </Field>

        <div style={{ marginTop: 'var(--sp-4)' }}>
          <div className="form-section__title">Adjuntos</div>

          {elegidos.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
              {elegidos.map((d) => (
                <span key={d.id} className="badge badge--info" style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--sp-1)' }}>
                  <Paperclip size={11} aria-hidden="true" />
                  {d.nombre_archivo}
                  <button
                    type="button"
                    onClick={() => alternar(d)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: 0 }}
                    aria-label={`Quitar ${d.nombre_archivo}`}
                  >
                    <X size={12} aria-hidden="true" />
                  </button>
                </span>
              ))}
            </div>
          )}

          {documentosFicha.length > 0 && (
            <div style={{ marginBottom: 'var(--sp-4)' }}>
              <p className="form-section__note" style={{ marginBottom: 'var(--sp-2)' }}>
                Documentos de esta ficha
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
                {documentosFicha.map((d) => (
                  <label key={d.id} className="checkbox">
                    <input
                      type="checkbox"
                      checked={elegidos.some((e) => e.id === d.id)}
                      onChange={() => alternar(d)}
                    />
                    <span>{d.nombre_archivo}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div
            onDragOver={(e) => {
              e.preventDefault()
              setArrastrando(true)
            }}
            onDragLeave={() => setArrastrando(false)}
            onDrop={(e) => {
              e.preventDefault()
              setArrastrando(false)
              anadirArchivos(e.dataTransfer.files)
            }}
            onClick={() => inputArchivoRef.current?.click()}
            style={{
              border: `1px dashed ${arrastrando ? 'var(--c-accent-strong)' : 'var(--c-border)'}`,
              borderRadius: 'var(--radius)',
              background: arrastrando ? 'var(--c-accent-soft)' : 'var(--c-surface-2)',
              padding: 'var(--sp-4)',
              textAlign: 'center',
              cursor: 'pointer',
              marginBottom: 'var(--sp-3)',
            }}
          >
            <Upload size={18} aria-hidden="true" style={{ marginBottom: 'var(--sp-1)' }} />
            <p className="form-section__note" style={{ margin: 0 }}>
              Arrastra aquí un archivo nuevo para enviarlo, o haz clic para elegirlo
            </p>
            <input
              ref={inputArchivoRef}
              type="file"
              multiple
              style={{ display: 'none' }}
              onChange={(e) => {
                anadirArchivos(e.target.files)
                e.target.value = ''
              }}
            />
          </div>

          {nuevosArchivos.length > 0 && (
            <div style={{ marginBottom: 'var(--sp-4)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)', marginBottom: 'var(--sp-2)' }}>
                {nuevosArchivos.map((archivo, i) => (
                  <div
                    key={`${archivo.name}-${i}`}
                    style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', fontSize: 'var(--fs-sm)' }}
                  >
                    <Paperclip size={13} aria-hidden="true" />
                    <span>{archivo.name}</span>
                    <span className="muted">{formatoTamano(archivo.size)}</span>
                    <button
                      type="button"
                      onClick={() => quitarArchivo(i)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', padding: 0 }}
                      aria-label={`Quitar ${archivo.name}`}
                    >
                      <X size={13} aria-hidden="true" />
                    </button>
                  </div>
                ))}
              </div>
              <Checkbox
                label="Guardar también en los documentos de esta ficha"
                checked={guardarEnFicha}
                onChange={setGuardarEnFicha}
              />
            </div>
          )}

          <p className="form-section__note" style={{ marginBottom: 'var(--sp-2)' }}>
            {documentosFicha.length > 0 ? '¿No está el que buscas? Búscalo en otras fichas' : 'Buscar un documento en otras fichas'}
          </p>
          <input
            className="input"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Nombre del archivo…"
          />

          {buscando && <p className="muted" style={{ marginTop: 'var(--sp-2)' }}>Buscando…</p>}

          {Object.entries(resultadosPorEntidad).map(([tipoEntidad, docs]) => (
            <div key={tipoEntidad} style={{ marginTop: 'var(--sp-3)' }}>
              <p className="form-section__note" style={{ margin: '0 0 var(--sp-1)', fontWeight: 650 }}>
                {ETIQUETA_ENTIDAD[tipoEntidad] ?? tipoEntidad}
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-1)' }}>
                {docs.map((d) => (
                  <label key={d.id} className="checkbox">
                    <input
                      type="checkbox"
                      checked={elegidos.some((e) => e.id === d.id)}
                      onChange={() => alternar(d)}
                    />
                    <span>
                      {d.nombre_archivo}
                      {d.entidad_codigo && <span className="muted"> · {d.entidad_codigo}</span>}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={enviando} onClick={() => void enviar()}>
          <Send size={16} aria-hidden="true" />
          {enviando ? 'Enviando…' : 'Enviar'}
        </button>
      </div>
    </Modal>
  )
}
