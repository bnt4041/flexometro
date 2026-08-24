import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Trash2, Upload } from 'lucide-react'

import { EmptyState, ErrorNotice, Tooltip } from './ui'
import { api, descargar } from '../lib/api'
import type { Documento, EntidadDocumento } from '../lib/api'

function formatoTamano(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatoFecha(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Pestaña "Documentos" (Fase 30) de cualquier objeto grande del negocio —
 *  subida y listado de ficheros guardados en MinIO (ver
 *  `app/core/storage.py` en el backend). */
export function Documentos({ entidad, entidadId }: { entidad: EntidadDocumento; entidadId: string }) {
  const [documentos, setDocumentos] = useState<Documento[]>([])
  const [error, setError] = useState<string | null>(null)
  const [subiendo, setSubiendo] = useState(false)
  const [arrastrando, setArrastrando] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const cargar = useCallback(async () => {
    try {
      setDocumentos(await api.documentos.list(entidad, entidadId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entidad, entidadId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function subirFicheros(ficheros: FileList | File[] | null) {
    const lista = ficheros ? Array.from(ficheros) : []
    if (lista.length === 0) return
    setSubiendo(true)
    setError(null)
    try {
      // Secuencial y no en paralelo: son subidas a MinIO de un tamaño
      // arbitrario, y varias a la vez complicarían saber cuál falló si el
      // usuario arrastra un lote grande.
      for (const fichero of lista) {
        await api.documentos.upload(entidad, entidadId, fichero)
      }
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setSubiendo(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function eliminar(documento: Documento) {
    if (!window.confirm(`¿Eliminar «${documento.nombre_archivo}»? No se puede deshacer.`)) return
    try {
      await api.documentos.remove(documento.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function bajar(documento: Documento) {
    try {
      await descargar(api.documentos.descargarUrl(documento.id), documento.nombre_archivo)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          Ficheros guardados sobre este registro.
        </p>
      </div>

      <ErrorNotice error={error} />

      <div
        onDragOver={(e) => {
          e.preventDefault()
          setArrastrando(true)
        }}
        onDragLeave={() => setArrastrando(false)}
        onDrop={(e) => {
          e.preventDefault()
          setArrastrando(false)
          void subirFicheros(e.dataTransfer.files)
        }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `1px dashed ${arrastrando ? 'var(--c-accent-strong)' : 'var(--c-border)'}`,
          borderRadius: 'var(--radius)',
          background: arrastrando ? 'var(--c-accent-soft)' : 'var(--c-surface-2)',
          padding: 'var(--sp-4)',
          textAlign: 'center',
          cursor: 'pointer',
          marginBottom: 'var(--sp-4)',
        }}
      >
        <Upload size={18} aria-hidden="true" style={{ marginBottom: 'var(--sp-1)' }} />
        <p className="form-section__note" style={{ margin: 0 }}>
          {subiendo ? 'Subiendo…' : 'Arrastra aquí uno o varios ficheros, o haz clic para elegirlos'}
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          disabled={subiendo}
          style={{ display: 'none' }}
          onChange={(e) => void subirFicheros(e.target.files)}
        />
      </div>

      {documentos.length === 0 ? (
        <EmptyState title="Sin documentos todavía">
          Sube planos, contratos o cualquier fichero relacionado con este registro.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Subido por</th>
                <th>Fecha</th>
                <th className="table__num">Tamaño</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {documentos.map((d) => (
                <tr key={d.id}>
                  <td>{d.nombre_archivo}</td>
                  <td>{d.creado_por_nombre ?? <span className="muted">—</span>}</td>
                  <td>{formatoFecha(d.created_at)}</td>
                  <td className="table__num">{formatoTamano(d.tamano_bytes)}</td>
                  <td className="table__actions">
                    <Tooltip texto="Descargar este documento">
                      <button className="btn btn--sm" onClick={() => void bajar(d)}>
                        <Download size={14} aria-hidden="true" />
                        Descargar
                      </button>
                    </Tooltip>{' '}
                    <Tooltip texto="Eliminar este documento">
                      <button
                        className="btn btn--sm btn--danger btn--solo-icono"
                        onClick={() => void eliminar(d)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </Tooltip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
