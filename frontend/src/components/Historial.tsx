import { useCallback, useEffect, useState } from 'react'

import { EmptyState, ErrorNotice } from './ui'
import type { AccionAuditoria, RegistroAuditoria } from '../lib/api'

function formatoFecha(iso: string): string {
  return new Date(iso).toLocaleString('es-ES', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** "razon_social" -> "Razón social" no es posible sin un diccionario de
 *  acentos por campo; nos quedamos con una humanización simple (guion bajo
 *  -> espacio, mayúscula inicial) — sigue siendo mucho más legible que el
 *  nombre de columna en crudo. */
function etiquetaCampo(campo: string): string {
  const texto = campo.replace(/_/g, ' ')
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

function formatoValor(valor: unknown): string {
  if (valor === null || valor === undefined) return '—'
  if (typeof valor === 'boolean') return valor ? 'Sí' : 'No'
  return String(valor)
}

const ETIQUETA_ACCION: Record<AccionAuditoria, string> = {
  creado: 'Creado',
  modificado: 'Modificado',
  eliminado: 'Eliminado',
  evento: 'IA',
}

const CLASE_ACCION: Record<AccionAuditoria, string> = {
  creado: 'badge--success',
  modificado: 'badge--info',
  eliminado: 'badge--danger',
  evento: 'badge--core',
}

/** Pestaña "Historial" (Fase 38) de cualquier ficha grande del negocio: quién
 *  creó, modificó o borró el registro y qué campos cambió, más reciente
 *  primero. Recibe la función de carga en vez de `entidad`/`entidadId` —a
 *  diferencia de Notas/Documentos, cada recurso vive bajo su propio router
 *  (mismo permiso que ya protege su ficha, incluido "solo lo mío"), así que
 *  no hay una única URL genérica que llamar. */
export function Historial({ cargar }: { cargar: () => Promise<RegistroAuditoria[]> }) {
  const [registros, setRegistros] = useState<RegistroAuditoria[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const recargar = useCallback(async () => {
    setCargando(true)
    try {
      setRegistros(await cargar())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void recargar()
  }, [recargar])

  if (cargando) return null

  return (
    <>
      <ErrorNotice error={error} />

      {registros.length === 0 ? (
        <EmptyState title="Sin historial todavía">
          Los cambios sobre este registro aparecerán aquí en cuanto se produzcan.
        </EmptyState>
      ) : (
        <div className="timeline">
          {registros.map((r) => (
            <div key={r.id} className={`timeline__item timeline__item--${r.accion}`}>
              <div className="timeline__meta">
                <span className={`badge ${CLASE_ACCION[r.accion]}`}>
                  {ETIQUETA_ACCION[r.accion]}
                </span>
                <span> {r.usuario_nombre ?? 'Alguien'}</span>
                <span className="muted"> · {formatoFecha(r.created_at)}</span>
              </div>
              {r.descripcion && <div className="timeline__cuerpo">{r.descripcion}</div>}
              {r.cambios && r.cambios.length > 0 && (
                <table className="table historial__cambios">
                  <tbody>
                    {r.cambios.map((c) => (
                      <tr key={c.campo}>
                        <td className="historial__campo">{etiquetaCampo(c.campo)}</td>
                        <td className="historial__antes">{formatoValor(c.antes)}</td>
                        <td className="historial__flecha">→</td>
                        <td className="historial__despues">{formatoValor(c.despues)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  )
}
