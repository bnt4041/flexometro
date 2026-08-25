import { useCallback, useEffect, useState } from 'react'

import { ETIQUETA_ESTADO_SOLICITUD, SolicitudFicha } from './SolicitudFicha'
import { EmptyState, ErrorNotice } from './ui'
import { api } from '../lib/api'
import type { NodoCapitulo, SolicitudPrecios } from '../lib/api'

/** Pestaña «Comparativo»: los paquetes de solicitud de precios de este
 *  presupuesto. Cada uno ("Yeserías") junta unas partidas y se manda a los
 *  proveedores que haga falta; la comparación de sus ofertas vive dentro de
 *  su ficha, que es donde compara algo homogéneo. */
export function Comparativo({
  presupuestoId,
  capitulos,
  onAprobado,
}: {
  presupuestoId: string
  capitulos: NodoCapitulo[]
  onAprobado: () => void
}) {
  const [solicitudes, setSolicitudes] = useState<SolicitudPrecios[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [abiertaId, setAbiertaId] = useState<string | null>(null)

  const recargar = useCallback(async () => {
    try {
      setSolicitudes(await api.solicitudesPrecios.listarPorPresupuesto(presupuestoId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [presupuestoId])

  useEffect(() => {
    void recargar()
  }, [recargar])

  // La ficha se referencia por id, no por objeto: así una recarga (tras
  // enviar, adjudicar o añadir un proveedor) la deja mostrando datos frescos
  // en vez de la copia con la que se abrió.
  const abierta = solicitudes?.find((s) => s.id === abiertaId) ?? null

  if (error && !solicitudes) return <ErrorNotice error={error} />
  if (!solicitudes) return <p className="muted">Cargando…</p>

  if (solicitudes.length === 0) {
    return (
      <EmptyState title="Todavía no hay ninguna solicitud de precios">
        Desde la pestaña de partidas, marca las que quieras agrupar (o pídelo de un capítulo
        entero) y usa «Solicitar precios…» en el menú contextual.
      </EmptyState>
    )
  }

  return (
    <div className="form-section">
      <ErrorNotice error={error} />

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Solicitud</th>
              <th>Estado</th>
              <th>Partidas</th>
              <th>Proveedores</th>
              <th>Han contestado</th>
              <th>Fecha límite</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {solicitudes.map((s) => {
              const contestados = s.destinatarios.filter((d) => d.estado === 'respondida').length
              return (
                <tr key={s.id}>
                  <td>
                    <strong>{s.titulo}</strong>
                    <div className="table__code">{s.codigo}</div>
                  </td>
                  <td>
                    <span className={`chip chip--estado-${s.estado}`}>
                      {ETIQUETA_ESTADO_SOLICITUD[s.estado] ?? s.estado}
                    </span>
                  </td>
                  <td className="table__num">{s.lineas.length}</td>
                  <td className="table__num">{s.destinatarios.length || '—'}</td>
                  <td className="table__num">{contestados || '—'}</td>
                  <td>{s.fecha_limite ?? <span className="muted">—</span>}</td>
                  <td className="table__actions">
                    <button className="btn btn--sm" onClick={() => setAbiertaId(s.id)}>
                      Abrir
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {abierta && (
        <SolicitudFicha
          solicitud={abierta}
          capitulos={capitulos}
          onClose={() => setAbiertaId(null)}
          onCambio={() => void recargar()}
          onAprobado={onAprobado}
        />
      )}
    </div>
  )
}
