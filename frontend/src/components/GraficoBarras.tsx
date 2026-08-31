import type { CampoInforme, FilaInforme } from '../lib/api'

/** Barras horizontales en SVG, sin librería de gráficos.
 *
 *  Horizontales y no verticales a propósito: las etiquetas de un informe son
 *  texto («Excavaciones Martínez SL», «en_ejecucion») y en vertical habría que
 *  girarlas o recortarlas. En horizontal se leen. */
export function GraficoBarras({
  filas,
  dimension,
  metrica,
}: {
  filas: FilaInforme[]
  dimension: CampoInforme
  metrica: CampoInforme
}) {
  const datos = filas
    .map((f) => ({
      etiqueta: String(f[dimension.nombre] ?? '—'),
      valor: Number(f[metrica.nombre] ?? 0),
    }))
    // Las primeras: un gráfico de 200 barras no se lee, se filtra.
    .slice(0, 15)

  const maximo = Math.max(...datos.map((d) => d.valor), 0)
  if (datos.length === 0 || maximo <= 0) {
    return <p className="muted">Nada que dibujar con estos datos.</p>
  }

  const alturaFila = 30
  const anchoEtiqueta = 190

  return (
    <svg
      width="100%"
      height={datos.length * alturaFila + 10}
      role="img"
      aria-label={`${metrica.etiqueta} por ${dimension.etiqueta}`}
    >
      {datos.map((d, i) => {
        const y = i * alturaFila
        // En porcentaje del ancho disponible: así el gráfico se adapta al
        // contenedor sin tener que medirlo en JavaScript.
        const ancho = (d.valor / maximo) * 100
        return (
          <g key={d.etiqueta + i}>
            <text
              x={anchoEtiqueta - 8}
              y={y + 19}
              textAnchor="end"
              fontSize="12"
              fill="var(--c-text, #111827)"
            >
              {d.etiqueta.length > 26 ? `${d.etiqueta.slice(0, 25)}…` : d.etiqueta}
            </text>
            <rect
              x={anchoEtiqueta}
              y={y + 6}
              width={`calc((100% - ${anchoEtiqueta + 70}px) * ${ancho / 100})`}
              height={18}
              rx={3}
              fill="var(--c-accent-strong, #f59e0b)"
            />
            <text
              x="100%"
              dx={-6}
              y={y + 19}
              textAnchor="end"
              fontSize="12"
              fill="var(--c-text-muted, #6b7280)"
            >
              {metrica.formato === 'dinero'
                ? d.valor.toLocaleString('es-ES', { minimumFractionDigits: 2 })
                : d.valor.toLocaleString('es-ES')}
            </text>
          </g>
        )
      })}
    </svg>
  )
}
