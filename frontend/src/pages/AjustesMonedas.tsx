import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw } from 'lucide-react'

import { ErrorNotice } from '../components/ui'
import { api } from '../lib/api'
import type { Moneda } from '../lib/api'
import { useToast } from '../toast'

function formatoFecha(iso: string | null): string {
  if (!iso) return 'Nunca'
  return new Date(iso).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
}

/** Monedas y tipo de cambio (Fase 23) — solo de referencia, la app sigue
 *  siendo 100% EUR para presupuestos y facturas reales. El tipo de cambio
 *  se refresca solo si lleva más de 24h caducado (ver
 *  `moneda_service.listar_monedas`); el botón fuerza un refresco
 *  inmediato. */
export function AjustesMonedas() {
  const { notificar } = useToast()
  const [monedas, setMonedas] = useState<Moneda[]>([])
  const [error, setError] = useState<string | null>(null)
  const [actualizando, setActualizando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setMonedas(await api.monedas.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function actualizar() {
    setActualizando(true)
    setError(null)
    try {
      setMonedas(await api.ajustes.monedas.actualizar())
      notificar('Tipos de cambio actualizados')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setActualizando(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Monedas</h1>
          <p className="page-lead">
            Solo de referencia: presupuestos y facturas siguen siendo siempre en euros. El tipo
            de cambio se toma del Banco Central Europeo.
          </p>
        </div>
        <Link className="btn" to="/ajustes">
          <ArrowLeft size={16} aria-hidden="true" />
          Volver a Ajustes
        </Link>
      </div>

      <div className="toolbar">
        <button className="btn btn--primary" disabled={actualizando} onClick={() => void actualizar()}>
          {!actualizando && <RefreshCw size={16} aria-hidden="true" />}
          {actualizando ? 'Actualizando…' : 'Actualizar ahora'}
        </button>
      </div>

      <ErrorNotice error={error} />

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Código</th>
              <th>Moneda</th>
              <th className="table__num">1 EUR =</th>
              <th>Actualizado</th>
            </tr>
          </thead>
          <tbody>
            {monedas.map((m) => (
              <tr key={m.id}>
                <td className="table__code">{m.codigo}</td>
                <td>
                  {m.nombre} <span className="muted">{m.simbolo}</span>
                </td>
                <td className="table__num">
                  {m.unidades_por_euro ?? <span className="muted">—</span>} {m.codigo !== 'EUR' && m.codigo}
                </td>
                <td className="muted">{formatoFecha(m.actualizado_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
