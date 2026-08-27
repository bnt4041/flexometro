/** Pestaña «Ventas» de la obra: lo que se certifica y lo que se factura.
 *
 *  Las certificaciones vivían dentro de la pestaña de Datos, mezcladas con las
 *  fechas y el personal. Su sitio es este: certificar es el paso previo a
 *  facturar, y las dos tablas se leen juntas o no se leen.
 *
 *  Igual que en Compras, se compone en el frontend: `facturacion` no ve
 *  `compras` ni al revés, así que ninguna vista que cruce los dos puede vivir
 *  en un endpoint del backend.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'

import {
  ETIQUETA_ESTADO_CERTIFICACION,
  ETIQUETA_ESTADO_FACTURA,
  ETIQUETA_SITUACION_COBRO,
  api,
} from '../lib/api'
import type { Certificacion, FacturaResumen } from '../lib/api'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'

export function VentasObra({
  obraId,
  certificaciones,
  onCertificar,
}: {
  obraId: string
  /** Las carga la ficha de la obra, que ya las necesita para su cabecera. */
  certificaciones: Certificacion[]
  onCertificar: () => void
}) {
  const [facturas, setFacturas] = useState<FacturaResumen[]>([])
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      const pagina = await api.facturas.list({ obra_id: obraId, limit: 200 })
      setFacturas(pagina.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [obraId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  // Solo cuentan las emitidas: una factura en borrador no se ha cobrado ni se
  // va a cobrar todavía, y meterla en el total daría una cifra falsa.
  const emitidas = facturas.filter((f) => f.estado === 'emitida')
  const facturado = emitidas.reduce((suma, f) => suma + Number(f.base_imponible), 0)
  const cobrado = emitidas.reduce((suma, f) => suma + Number(f.cobrado), 0)
  const pendiente = emitidas.reduce((suma, f) => suma + Number(f.pendiente), 0)
  const vencidas = emitidas.filter((f) => f.vencida).length

  return (
    <div className="form-section">
      <ErrorNotice error={error} />

      <div className="cuadre">
        <div className="cuadre__dato">
          <span className="cuadre__etiqueta">Facturado (base, emitidas)</span>
          <strong>{formatoImporte(String(facturado))} €</strong>
        </div>
        <div className="cuadre__dato">
          <span className="cuadre__etiqueta">Cobrado</span>
          <strong>{formatoImporte(String(cobrado))} €</strong>
        </div>
        <div className="cuadre__dato">
          <span className="cuadre__etiqueta">Pendiente de cobro</span>
          <strong className={pendiente > 0 ? 'cuadre--ojo' : undefined}>
            {formatoImporte(String(pendiente))} €
          </strong>
        </div>
        <div className="cuadre__dato">
          <span className="cuadre__etiqueta">Facturas vencidas</span>
          <strong className={vencidas > 0 ? 'cuadre--ojo' : undefined}>{vencidas}</strong>
        </div>
      </div>

      <div className="page-head">
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Certificaciones</h2>
        <Tooltip texto="Certificar lo ejecutado hasta la fecha">
          <button className="btn" onClick={onCertificar}>
            <Plus size={16} aria-hidden="true" />
            Nueva certificación
          </button>
        </Tooltip>
      </div>

      <div className="table-wrap">
        {certificaciones.length === 0 ? (
          <EmptyState title="Sin certificaciones">
            Certifica lo ejecutado hasta la fecha para poder facturarlo.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Certificación</th>
                <th>Nº</th>
                <th>Fecha</th>
                <th>Estado</th>
                <th className="table__num">Retención</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {certificaciones.map((c) => (
                <tr key={c.id}>
                  <td>{c.codigo}</td>
                  <td className="table__num">{c.numero}</td>
                  <td>{c.fecha}</td>
                  <td>
                    <span className={`chip chip--estado-cert-${c.estado}`}>
                      {ETIQUETA_ESTADO_CERTIFICACION[c.estado]}
                    </span>
                  </td>
                  <td className="table__num">{formatoImporte(c.retencion_garantia_pct, 2)} %</td>
                  <td className="table__actions">
                    <Link className="btn btn--sm" to={`/certificaciones/${c.id}`}>
                      Abrir
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="page-head" style={{ marginTop: 'var(--sp-6)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Facturas de venta</h2>
      </div>

      <div className="table-wrap">
        {facturas.length === 0 ? (
          <EmptyState title="Sin facturas">
            Las facturas se emiten desde una certificación, o sueltas desde el módulo de
            Facturación indicando esta obra.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Factura</th>
                <th>Cliente</th>
                <th>Emisión</th>
                <th>Vence</th>
                <th className="table__num">Base</th>
                <th className="table__num">Total</th>
                <th>Estado</th>
                <th>Cobro</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {facturas.map((f) => (
                <tr key={f.id}>
                  <td>
                    {f.codigo}
                    {f.certificacion_id && (
                      <div className="table__code">de una certificación</div>
                    )}
                  </td>
                  <td>{f.cliente_razon_social}</td>
                  <td>{f.fecha_emision ?? <span className="muted">—</span>}</td>
                  <td>
                    {f.fecha_vencimiento ? (
                      f.vencida ? (
                        <Tooltip texto="Vencida y sin cobrar del todo">
                          <span className="cuadre--ojo">{f.fecha_vencimiento}</span>
                        </Tooltip>
                      ) : (
                        f.fecha_vencimiento
                      )
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td className="table__num">{formatoImporte(f.base_imponible)} €</td>
                  <td className="table__num">
                    <strong>{formatoImporte(f.total)} €</strong>
                  </td>
                  <td>
                    <span className={`chip chip--estado-${f.estado}`}>
                      {ETIQUETA_ESTADO_FACTURA[f.estado]}
                    </span>
                  </td>
                  <td>{ETIQUETA_SITUACION_COBRO[f.situacion_cobro]}</td>
                  <td className="table__actions">
                    <Link className="btn btn--sm" to={`/facturas/${f.id}`}>
                      Abrir
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
