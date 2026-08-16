import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ErrorNotice, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { InformeCosteObra } from '../lib/api'

export function CosteReal() {
  const { id = '' } = useParams()
  const [informe, setInforme] = useState<InformeCosteObra | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api.obras
      .costes(id)
      .then(setInforme)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [id])

  if (error) return <ErrorNotice error={error} />
  if (!informe) return <p className="muted">Cargando…</p>

  return (
    <>
      <div className="breadcrumb">
        <Link to="/obras">Obras</Link> / <Link to={`/obras/${id}`}>{informe.obra_codigo}</Link> /
        coste real
      </div>

      <h1 className="page-title">Coste real vs. presupuestado</h1>
      <p className="page-lead">
        {informe.obra_nombre}. Cada fila compara lo presupuestado directamente en ese capítulo
        (sin arrastrar subcapítulos) con lo que de verdad se ha gastado en materiales y mano de
        obra imputados a él.
      </p>

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Capítulo</th>
              <th className="table__num">Presupuestado</th>
              <th className="table__num">Materiales</th>
              <th className="table__num">Mano de obra</th>
              <th className="table__num">Real total</th>
              <th className="table__num">Desviación</th>
            </tr>
          </thead>
          <tbody>
            {informe.capitulos.map((c) => (
              <FilaCoste key={c.capitulo_id ?? 'sin-asignar'} fila={c} />
            ))}
          </tbody>
          <tfoot>
            <tr className="fila-total">
              <td className="total-label">{informe.totales.resumen}</td>
              <td className="table__num">{formatoImporte(informe.totales.presupuestado)}</td>
              <td className="table__num">{formatoImporte(informe.totales.real_materiales)}</td>
              <td className="table__num">{formatoImporte(informe.totales.real_mano_obra)}</td>
              <td className="table__num">
                <strong>{formatoImporte(informe.totales.real_total)}</strong>
              </td>
              <td className="table__num">
                <Desviacion valor={informe.totales.desviacion} pct={informe.totales.desviacion_pct} />
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </>
  )
}

function FilaCoste({ fila }: { fila: InformeCosteObra['capitulos'][number] }) {
  return (
    <tr>
      <td>
        {fila.codigo !== '—' && <span className="table__code">{fila.codigo} </span>}
        {fila.resumen}
      </td>
      <td className="table__num">{formatoImporte(fila.presupuestado)}</td>
      <td className="table__num">{formatoImporte(fila.real_materiales)}</td>
      <td className="table__num">{formatoImporte(fila.real_mano_obra)}</td>
      <td className="table__num">
        <strong>{formatoImporte(fila.real_total)}</strong>
      </td>
      <td className="table__num">
        <Desviacion valor={fila.desviacion} pct={fila.desviacion_pct} />
      </td>
    </tr>
  )
}

function Desviacion({ valor, pct }: { valor: string; pct: string | null }) {
  const numero = Number(valor)
  const color = numero > 0 ? 'var(--c-danger)' : numero < 0 ? 'var(--c-success)' : undefined
  return (
    <span style={{ color }}>
      {numero > 0 ? '+' : ''}
      {formatoImporte(valor)}
      {pct !== null && <span className="muted"> ({pct}%)</span>}
    </span>
  )
}
