import { useCallback, useEffect, useMemo, useState } from 'react'
import { Check } from 'lucide-react'

import { ETIQUETA_ESTADO_SOLICITUD, SolicitudFicha } from './SolicitudFicha'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { NodoCapitulo, SolicitudPrecios } from '../lib/api'
import { useToast } from '../toast'

interface FilaComparativo {
  partidaId: string
  capituloResumen: string | null
  resumen: string
  unidad: string
  medicion: string
  precioActual: string | null
}

function preciosActuales(capitulos: NodoCapitulo[]): Map<string, string> {
  const mapa = new Map<string, string>()
  function recorrer(nodos: NodoCapitulo[]) {
    for (const nodo of nodos) {
      for (const partida of nodo.partidas) mapa.set(partida.id, partida.precio)
      recorrer(nodo.hijos)
    }
  }
  recorrer(capitulos)
  return mapa
}

/** Pestaña «Comparativo» (Fase 53): las solicitudes de precios de este
 *  presupuesto — cada una con su ficha propia — y, debajo, la comparativa
 *  cruzada de lo que ha ofertado cada proveedor.
 *
 *  Aprobar un precio sustituye el descompuesto de la partida ORIGINAL por la
 *  subcontrata de ese proveedor; la oferta en sí queda intacta como
 *  presupuesto de proveedor, solo se referencia. */
export function Comparativo({
  presupuestoId,
  capitulos,
  onAprobado,
}: {
  presupuestoId: string
  capitulos: NodoCapitulo[]
  onAprobado: () => void
}) {
  const { notificar } = useToast()
  const [solicitudes, setSolicitudes] = useState<SolicitudPrecios[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [aprobando, setAprobando] = useState<string | null>(null)
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

  const precioPorPartida = useMemo(() => preciosActuales(capitulos), [capitulos])

  // La ficha se referencia por id, no por objeto: así una recarga (tras
  // enviar, aprobar o duplicar) la deja mostrando datos frescos en vez de la
  // copia con la que se abrió.
  const abierta = solicitudes?.find((s) => s.id === abiertaId) ?? null

  /** Solo las que ya han salido: un borrador no tiene nada que comparar
   *  todavía y solo ensuciaría la matriz con una columna vacía. */
  const conOferta = useMemo(
    () => (solicitudes ?? []).filter((s) => s.lineas.some((l) => l.precio_ofertado != null)),
    [solicitudes],
  )

  const filas = useMemo<FilaComparativo[]>(() => {
    const vistas = new Map<string, FilaComparativo>()
    for (const s of conOferta) {
      for (const l of s.lineas) {
        if (!l.partida_id || vistas.has(l.partida_id)) continue
        vistas.set(l.partida_id, {
          partidaId: l.partida_id,
          capituloResumen: l.capitulo_resumen,
          resumen: l.resumen,
          unidad: l.unidad,
          medicion: l.medicion,
          precioActual: precioPorPartida.get(l.partida_id) ?? null,
        })
      }
    }
    return [...vistas.values()]
  }, [conOferta, precioPorPartida])

  async function aprobar(solicitudId: string, lineaId: string) {
    setAprobando(lineaId)
    setError(null)
    try {
      await api.solicitudesPrecios.aprobarLinea(solicitudId, lineaId)
      await recargar()
      notificar('Precio aprobado: el descompuesto de la partida se ha actualizado')
      onAprobado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setAprobando(null)
    }
  }

  if (error && !solicitudes) return <ErrorNotice error={error} />
  if (!solicitudes) return <p className="muted">Cargando…</p>

  if (solicitudes.length === 0) {
    return (
      <EmptyState title="Todavía no se ha pedido precio a ningún proveedor">
        Desde la pestaña de partidas, marca una o varias (o pídelo de un capítulo entero) y usa
        «Solicitar precios…» en el menú contextual.
      </EmptyState>
    )
  }

  return (
    <div className="form-section">
      <ErrorNotice error={error} />

      <p className="field__label">Solicitudes de precios</p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Código</th>
              <th>Proveedor</th>
              <th>Estado</th>
              <th>Partidas</th>
              <th>Ofertadas</th>
              <th>Fecha límite</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {solicitudes.map((s) => {
              const ofertadas = s.lineas.filter((l) => l.precio_ofertado != null).length
              return (
                <tr key={s.id}>
                  <td className="table__code">{s.codigo}</td>
                  <td>
                    <button className="table__link" onClick={() => setAbiertaId(s.id)}>
                      {s.proveedor_razon_social}
                    </button>
                    {!s.proveedor_email && <div className="muted">sin correo</div>}
                  </td>
                  <td>
                    <span className={`chip chip--estado-${s.estado}`}>
                      {ETIQUETA_ESTADO_SOLICITUD[s.estado] ?? s.estado}
                    </span>
                  </td>
                  <td className="table__num">{s.lineas.length}</td>
                  <td className="table__num">{ofertadas || '—'}</td>
                  <td>{s.fecha_limite ?? <span className="muted">—</span>}</td>
                  <td className="table__actions">
                    <button className="btn btn--sm" onClick={() => setAbiertaId(s.id)}>
                      {s.estado === 'borrador' ? 'Editar y enviar' : 'Abrir'}
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {conOferta.length > 0 && (
        <>
          <p className="field__label" style={{ marginTop: 'var(--sp-5)' }}>
            Comparativa de precios recibidos
          </p>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Partida</th>
                  <th>Medición</th>
                  <th>Precio actual</th>
                  {conOferta.map((s) => (
                    <th key={s.id}>{s.proveedor_razon_social}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filas.map((fila) => {
                  const celdas = conOferta.map((s) => ({
                    solicitud: s,
                    linea: s.lineas.find((l) => l.partida_id === fila.partidaId) ?? null,
                  }))
                  const mejorPrecio = celdas
                    .map((c) => (c.linea?.precio_ofertado ? Number(c.linea.precio_ofertado) : null))
                    .filter((v): v is number => v !== null)
                    .reduce((min, v) => (min === null || v < min ? v : min), null as number | null)

                  return (
                    <tr key={fila.partidaId}>
                      <td>
                        <span className="muted">{fila.capituloResumen}</span>
                        <br />
                        {fila.resumen}
                      </td>
                      <td className="table__num">
                        {fila.medicion} {fila.unidad}
                      </td>
                      <td className="table__num">
                        {fila.precioActual ? `${formatoImporte(fila.precioActual)} €` : '—'}
                      </td>
                      {celdas.map(({ solicitud, linea }) => {
                        if (!linea || linea.precio_ofertado == null) {
                          return (
                            <td key={solicitud.id} className="muted">
                              —
                            </td>
                          )
                        }
                        const esMejor =
                          mejorPrecio !== null && Number(linea.precio_ofertado) === mejorPrecio
                        return (
                          <td key={solicitud.id}>
                            <div
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 'var(--sp-2)',
                                fontWeight: esMejor ? 600 : undefined,
                              }}
                            >
                              <span className="table__num">
                                {formatoImporte(linea.precio_ofertado)} €
                              </span>
                              {linea.aprobada ? (
                                <span className="badge badge--success">
                                  <Check size={12} aria-hidden="true" /> Aprobada
                                </span>
                              ) : (
                                <Tooltip texto="Sustituye el descompuesto de la partida por esta subcontrata">
                                  <button
                                    className="btn btn--sm"
                                    disabled={aprobando === linea.id}
                                    onClick={() => void aprobar(solicitud.id, linea.id)}
                                  >
                                    {aprobando === linea.id ? 'Aprobando…' : 'Aprobar'}
                                  </button>
                                </Tooltip>
                              )}
                            </div>
                            {linea.observaciones_proveedor && (
                              <div className="muted">{linea.observaciones_proveedor}</div>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

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
