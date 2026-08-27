import { useCallback, useEffect, useState } from 'react'

import { ETIQUETA_ESTADO_SOLICITUD, SolicitudFicha } from './SolicitudFicha'
import { EmptyState, ErrorNotice } from './ui'
import { api } from '../lib/api'
import type { NodoCapitulo, SolicitudPrecios } from '../lib/api'

/** Pestaña «Comparativo»: los paquetes de solicitud de precios. Cada uno
 *  ("Yeserías") junta unas partidas y se manda a los proveedores que haga
 *  falta; la comparación de sus ofertas vive dentro de su ficha, que es donde
 *  compara algo homogéneo.
 *
 *  Sirve dos sitios. En un **presupuesto** se le pasan `presupuestoId` y sus
 *  `capitulos`, que ya están cargados. En una **obra** se le pasa `obraId` y
 *  reúne los de todos sus presupuestos, principal y anexos — que es donde de
 *  verdad se consulta: saber a quién se adjudicó cada partida es el punto de
 *  partida de las compras. Ahí los capítulos no se conocen de antemano (cada
 *  solicitud puede ser de un presupuesto distinto), así que se cargan al abrir
 *  una: es un viaje más, pero solo cuando hace falta y con los datos correctos.
 */
export function Comparativo({
  presupuestoId,
  obraId,
  capitulos,
  codigosPresupuesto,
  onAprobado,
}: {
  presupuestoId?: string
  obraId?: string
  capitulos?: NodoCapitulo[]
  /** Solo en modo obra: `presupuesto_id → código`, para etiquetar cada fila. */
  codigosPresupuesto?: Map<string, string>
  onAprobado: () => void
}) {
  const [solicitudes, setSolicitudes] = useState<SolicitudPrecios[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [abiertaId, setAbiertaId] = useState<string | null>(null)
  // En modo obra los capítulos de la solicitud abierta se piden al abrirla.
  const [capitulosAbierta, setCapitulosAbierta] = useState<NodoCapitulo[]>([])

  const recargar = useCallback(async () => {
    try {
      setSolicitudes(
        obraId
          ? await api.solicitudesPrecios.listarPorObra(obraId)
          : await api.solicitudesPrecios.listarPorPresupuesto(presupuestoId!),
      )
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [obraId, presupuestoId])

  useEffect(() => {
    void recargar()
  }, [recargar])

  async function abrir(solicitud: SolicitudPrecios) {
    if (!obraId) {
      setAbiertaId(solicitud.id)
      return
    }
    try {
      const presupuesto = await api.presupuestos.get(solicitud.presupuesto_id)
      setCapitulosAbierta(presupuesto.capitulos)
      setAbiertaId(solicitud.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  // La ficha se referencia por id, no por objeto: así una recarga (tras
  // enviar, adjudicar o añadir un proveedor) la deja mostrando datos frescos
  // en vez de la copia con la que se abrió.
  const abierta = solicitudes?.find((s) => s.id === abiertaId) ?? null

  if (error && !solicitudes) return <ErrorNotice error={error} />
  if (!solicitudes) return <p className="muted">Cargando…</p>

  if (solicitudes.length === 0) {
    return (
      <EmptyState title="Todavía no hay ninguna solicitud de precios">
        {obraId
          ? 'Las solicitudes se piden desde el presupuesto: marca allí las partidas y usa ' +
            '«Solicitar precios…». Aquí aparecen las de todos los presupuestos de la obra.'
          : 'Desde la pestaña de partidas, marca las que quieras agrupar (o pídelo de un ' +
            'capítulo entero) y usa «Solicitar precios…» en el menú contextual.'}
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
              {obraId && <th>Presupuesto</th>}
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
                  {obraId && (
                    <td className="table__code">
                      {codigosPresupuesto?.get(s.presupuesto_id) ?? '—'}
                    </td>
                  )}
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
                    <button className="btn btn--sm" onClick={() => void abrir(s)}>
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
          capitulos={obraId ? capitulosAbierta : (capitulos ?? [])}
          onClose={() => setAbiertaId(null)}
          onCambio={() => void recargar()}
          onAprobado={onAprobado}
        />
      )}
    </div>
  )
}
