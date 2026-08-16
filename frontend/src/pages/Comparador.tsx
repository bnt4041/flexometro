import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { EmptyState, ErrorNotice, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { Cambio, Comparacion } from '../lib/api'

export function Comparador() {
  const { id = '', otroId = '' } = useParams()
  const [datos, setDatos] = useState<Comparacion | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api.presupuestos
      .comparar(id, otroId)
      .then(setDatos)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [id, otroId])

  if (error) return <ErrorNotice error={error} />
  if (!datos) return <p className="muted">Cargando…</p>

  const delta = Number(datos.delta_total)

  return (
    <>
      <div className="breadcrumb">
        <Link to="/presupuestos">Presupuestos</Link> /{' '}
        <Link to={`/presupuestos/${id}`}>{datos.a.codigo}</Link> / comparar
      </div>

      <h1 className="page-title">
        {datos.a.codigo} <span className="muted">→</span> {datos.b.codigo}
      </h1>
      <p className="page-lead">
        Versión {datos.a.version} frente a versión {datos.b.version}, partida a partida. La
        comparación empareja por capítulo y código.
      </p>

      <div className="card resumen-totales" style={{ marginLeft: 0, marginTop: 0 }}>
        <div className="resumen-totales__fila">
          <span>
            {datos.a.codigo} · v{datos.a.version}
          </span>
          <span className="resumen-totales__valor">{formatoImporte(datos.total_a)} €</span>
        </div>
        <div className="resumen-totales__fila">
          <span>
            {datos.b.codigo} · v{datos.b.version}
          </span>
          <span className="resumen-totales__valor">{formatoImporte(datos.total_b)} €</span>
        </div>
        <div className="resumen-totales__fila is-total">
          <span>Diferencia</span>
          <span
            className="resumen-totales__valor"
            style={{ color: delta > 0 ? 'var(--c-danger)' : 'var(--c-success)' }}
          >
            {delta > 0 ? '+' : ''}
            {formatoImporte(datos.delta_total)} €
          </span>
        </div>
      </div>

      <Bloque
        titulo="Partidas nuevas"
        vacio="Ninguna partida nueva."
        cambios={datos.altas}
        columna="b"
      />
      <Bloque
        titulo="Partidas eliminadas"
        vacio="No se ha quitado ninguna partida."
        cambios={datos.bajas}
        columna="a"
      />
      <Bloque
        titulo="Partidas modificadas"
        vacio="Ninguna partida ha cambiado de medición ni de precio."
        cambios={datos.cambios}
        columna="ambas"
      />

      <p className="muted" style={{ marginTop: 'var(--sp-4)' }}>
        {datos.sin_cambios} {datos.sin_cambios === 1 ? 'partida idéntica' : 'partidas idénticas'}{' '}
        en ambas versiones.
      </p>
    </>
  )
}

function Bloque({
  titulo,
  vacio,
  cambios,
  columna,
}: {
  titulo: string
  vacio: string
  cambios: Cambio[]
  columna: 'a' | 'b' | 'ambas'
}) {
  return (
    <>
      <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, margin: 'var(--sp-6) 0 var(--sp-3)' }}>
        {titulo} <span className="muted">({cambios.length})</span>
      </h2>
      <div className="table-wrap">
        {cambios.length === 0 ? (
          <EmptyState title={vacio} />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Descripción</th>
                {columna === 'ambas' ? (
                  <>
                    <th className="table__num">Medición</th>
                    <th className="table__num">Precio</th>
                    <th className="table__num">Importe</th>
                    <th className="table__num">Diferencia</th>
                  </>
                ) : (
                  <>
                    <th className="table__num">Medición</th>
                    <th className="table__num">Precio</th>
                    <th className="table__num">Importe</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {cambios.map((c) => {
                const d = Number(c.delta)
                return (
                  <tr key={c.codigo + c.resumen}>
                    <td className="table__code">{c.codigo}</td>
                    <td>
                      {c.resumen} <span className="muted">({c.unidad})</span>
                    </td>
                    {columna === 'ambas' ? (
                      <>
                        <td className="table__num">
                          <span className="muted">{formatoImporte(c.medicion_a, 3)}</span> →{' '}
                          {formatoImporte(c.medicion_b, 3)}
                        </td>
                        <td className="table__num">
                          <span className="muted">{formatoImporte(c.precio_a)}</span> →{' '}
                          {formatoImporte(c.precio_b)}
                        </td>
                        <td className="table__num">{formatoImporte(c.importe_b)}</td>
                        <td
                          className="table__num"
                          style={{ color: d > 0 ? 'var(--c-danger)' : 'var(--c-success)' }}
                        >
                          {d > 0 ? '+' : ''}
                          {formatoImporte(c.delta)}
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="table__num">
                          {formatoImporte(columna === 'a' ? c.medicion_a : c.medicion_b, 3)}
                        </td>
                        <td className="table__num">
                          {formatoImporte(columna === 'a' ? c.precio_a : c.precio_b)}
                        </td>
                        <td className="table__num">
                          <strong>
                            {formatoImporte(columna === 'a' ? c.importe_a : c.importe_b)}
                          </strong>
                        </td>
                      </>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
