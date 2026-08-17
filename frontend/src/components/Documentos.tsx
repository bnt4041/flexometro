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

  async function subirFichero(fichero: File | null) {
    if (!fichero) return
    setSubiendo(true)
    setError(null)
    try {
      await api.documentos.upload(entidad, entidadId, fichero)
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
        <Tooltip texto="Subir un fichero nuevo">
          <button
            className="btn"
            disabled={subiendo}
            onClick={() => inputRef.current?.click()}
          >
            <Upload size={16} aria-hidden="true" />
            {subiendo ? 'Subiendo…' : 'Subir documento'}
          </button>
        </Tooltip>
        <input
          ref={inputRef}
          type="file"
          style={{ display: 'none' }}
          onChange={(e) => void subirFichero(e.target.files?.[0] ?? null)}
        />
      </div>

      <ErrorNotice error={error} />

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
