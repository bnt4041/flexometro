/** Cuadro de mandos de la obra: la primera pantalla al abrirla.
 *
 *  Reúne lo que hasta ahora había que ir a buscar a cuatro sitios: el árbol
 *  (lo contratado), el informe de coste real, las compras y las ventas. Se
 *  compone en el frontend porque ningún módulo del backend ve a la vez
 *  `compras` y `facturacion` — son hermanos y el detector de ciclos lo impide.
 *
 *  Sobre las formas: las cifras sueltas son **tarjetas**, no gráficos de una
 *  barra. Lo certificado sobre el contrato es un **medidor**. Y la desviación
 *  por capítulo es lo único que de verdad pide un gráfico, porque lo que hay
 *  que leer es la polaridad (por encima o por debajo de lo previsto): barra
 *  divergente con el cero en el centro.
 */

import { useCallback, useEffect, useState } from 'react'
import { ArrowDown, ArrowUp, BarChart3, Table2 } from 'lucide-react'

import { api } from '../lib/api'
import type {
  AlbaranResumen,
  ArbolObra,
  Certificacion,
  CosteCapitulo,
  InformeCosteObra,
  ResumenTareasObra,
  ResumenVentasObra,
  Tarea,
  TotalesComprasObra,
} from '../lib/api'
import { EmptyState, ErrorNotice, Tooltip, formatoImporte } from './ui'

function euros(valor: string | number): string {
  return `${formatoImporte(String(valor))} €`
}

/** Una cifra con su contexto. No es un gráfico de una barra: es el número. */
function Tarjeta({
  etiqueta,
  valor,
  nota,
  alerta,
}: {
  etiqueta: string
  valor: string
  nota?: string
  alerta?: boolean
}) {
  return (
    <div className="tarjeta-kpi">
      <span className="tarjeta-kpi__etiqueta">{etiqueta}</span>
      <strong className={`tarjeta-kpi__valor${alerta ? ' tarjeta-kpi__valor--ojo' : ''}`}>
        {valor}
      </strong>
      {nota && <span className="tarjeta-kpi__nota">{nota}</span>}
    </div>
  )
}

/** Medidor: una razón contra un límite. El relleno lleva el estado y la pista
 *  sin rellenar es un paso claro de la misma rampa, para que se lea a lo largo
 *  de toda la barra. El porcentaje va escrito: el color no es el único canal. */
function Medidor({
  etiqueta,
  parte,
  total,
  detalle,
}: {
  etiqueta: string
  parte: number
  total: number
  detalle?: string
}) {
  const pct = total > 0 ? (parte / total) * 100 : 0
  // Se recorta al 100 % para dibujar, pero el número real se sigue diciendo:
  // pasarse del contrato es justo lo que hay que ver.
  const ancho = Math.min(100, Math.max(0, pct))
  const pasado = pct > 100
  return (
    <div className="medidor">
      <div className="medidor__cabecera">
        <span className="medidor__etiqueta">{etiqueta}</span>
        <span className="medidor__pct">{pct.toFixed(1)} %</span>
      </div>
      <div
        className="medidor__pista"
        role="meter"
        aria-valuenow={Number(pct.toFixed(1))}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={etiqueta}
      >
        <div
          className={`medidor__relleno${pasado ? ' medidor__relleno--pasado' : ''}`}
          style={{ width: `${ancho}%` }}
        />
      </div>
      <span className="medidor__detalle">
        {detalle ?? `${euros(parte)} de ${euros(total)}`}
      </span>
    </div>
  )
}

/** Desviación por capítulo: barra divergente centrada en el cero.
 *
 *  La pareja de colores NO es rojo-verde: entre los tokens de éxito y peligro
 *  de la aplicación hay ΔE 4,2 en deuteranopia, o sea que las dos barras son
 *  la misma para quien no distingue rojo y verde. Se usa rojo contra el azul de
 *  marca (ΔE 20,8, las seis comprobaciones en verde), y además cada barra lleva
 *  su importe con signo y una flecha, así que el color es el tercer canal, no
 *  el único.
 */
function DesviacionPorCapitulo({ capitulos }: { capitulos: CosteCapitulo[] }) {
  const [comoTabla, setComoTabla] = useState(false)

  // Solo los capítulos con algo que decir: sin presupuesto ni coste real, la
  // fila es ruido.
  const conDatos = capitulos.filter(
    (c) => Number(c.presupuestado) !== 0 || Number(c.real_total) !== 0,
  )
  if (conDatos.length === 0) {
    return (
      <EmptyState title="Todavía no hay desviación que comparar">
        Hará falta coste real: albaranes de material o partes de trabajo imputados a la obra.
      </EmptyState>
    )
  }

  // La escala es común a las dos alas para que las barras sean comparables
  // entre sí: media pista para cada lado.
  const tope = Math.max(...conDatos.map((c) => Math.abs(Number(c.desviacion))), 1)

  return (
    <div className="desviacion">
      <div className="desviacion__barra-superior">
        <span className="desviacion__leyenda">
          <span className="desviacion__muestra desviacion__muestra--ahorro" />
          Por debajo de lo previsto
          <span className="desviacion__muestra desviacion__muestra--sobrecoste" />
          Sobrecoste
        </span>
        <Tooltip texto={comoTabla ? 'Ver como gráfico' : 'Ver como tabla'}>
          <button className="btn btn--sm" onClick={() => setComoTabla((v) => !v)}>
            {comoTabla ? <BarChart3 size={14} /> : <Table2 size={14} />}
            {comoTabla ? 'Gráfico' : 'Tabla'}
          </button>
        </Tooltip>
      </div>

      {comoTabla ? (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Capítulo</th>
                <th className="table__num">Presupuestado</th>
                <th className="table__num">Real</th>
                <th className="table__num">Desviación</th>
                <th className="table__num">%</th>
              </tr>
            </thead>
            <tbody>
              {conDatos.map((c) => (
                <tr key={c.capitulo_id ?? c.codigo}>
                  <td>{c.resumen}</td>
                  <td className="table__num">{euros(c.presupuestado)}</td>
                  <td className="table__num">{euros(c.real_total)}</td>
                  <td className="table__num">{euros(c.desviacion)}</td>
                  <td className="table__num">
                    {c.desviacion_pct === null ? '—' : `${formatoImporte(c.desviacion_pct, 1)} %`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ul className="desviacion__lista">
          {conDatos.map((c) => {
            const valor = Number(c.desviacion)
            // El informe la calcula como real − presupuestado
            // (`compras/costes.py`): POSITIVA es sobrecoste. Invertirlo aquí
            // pintaría cada desvío como si fuera un ahorro.
            const sobrecoste = valor > 0
            const ancho = (Math.abs(valor) / tope) * 50
            return (
              <li key={c.capitulo_id ?? c.codigo} className="desviacion__fila">
                <span className="desviacion__nombre" title={c.resumen}>
                  {c.resumen}
                </span>
                {/* El desglose va al pasar por encima: la barra sola dice
                    cuánto se desvía, no contra qué. */}
                <Tooltip
                  texto={`Presupuestado ${euros(c.presupuestado)} · real ${euros(
                    c.real_total,
                  )} (material ${euros(c.real_materiales)} + mano de obra ${euros(
                    c.real_mano_obra,
                  )})${
                    c.desviacion_pct === null
                      ? ''
                      : ` · ${formatoImporte(c.desviacion_pct, 1)} %`
                  }`}
                >
                  <span className="desviacion__pista">
                    <span className="desviacion__cero" aria-hidden="true" />
                    <span
                      className={`desviacion__marca desviacion__marca--${
                        sobrecoste ? 'sobrecoste' : 'ahorro'
                      }`}
                      style={
                        sobrecoste
                          ? { left: '50%', width: `${ancho}%` }
                          : { right: '50%', width: `${ancho}%` }
                      }
                    />
                  </span>
                </Tooltip>
                <span
                  className={`desviacion__valor desviacion__valor--${
                    sobrecoste ? 'sobrecoste' : 'ahorro'
                  }`}
                >
                  {sobrecoste ? (
                    <ArrowUp size={12} aria-hidden="true" />
                  ) : (
                    <ArrowDown size={12} aria-hidden="true" />
                  )}
                  {euros(Math.abs(valor))}
                </span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

export function CuadroObra({
  obraId,
  arbol,
  certificaciones,
  refresco = 0,
}: {
  obraId: string
  /** Ya lo tiene cargado la ficha: es lo contratado, la referencia de todo. */
  arbol: ArbolObra | null
  certificaciones: Certificacion[]
  /** Cambia cuando se toca una tarea en su pestaña, para recargar el widget. */
  refresco?: number
}) {
  const [costes, setCostes] = useState<InformeCosteObra | null>(null)
  const [compras, setCompras] = useState<TotalesComprasObra | null>(null)
  const [ventas, setVentas] = useState<ResumenVentasObra | null>(null)
  const [albaranes, setAlbaranes] = useState<AlbaranResumen[]>([])
  const [tareas, setTareas] = useState<ResumenTareasObra | null>(null)
  const [proximas, setProximas] = useState<Tarea[]>([])
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    // `allSettled` a propósito: si a la cuenta le falta el módulo de
    // facturación (o el de compras), el resto del cuadro tiene que seguir
    // apareciendo en vez de quedarse en blanco por un 403.
    const [c, cp, v, alb, rt, lt] = await Promise.allSettled([
      api.obras.costes(obraId),
      api.facturasRecibidas.totalesDeObra(obraId),
      api.certificaciones.resumenDeObra(obraId),
      api.albaranes.list({ obra_id: obraId, limit: 5 }),
      api.obras.resumenTareas(obraId),
      api.obras.tareas(obraId),
    ])
    setCostes(c.status === 'fulfilled' ? c.value : null)
    setCompras(cp.status === 'fulfilled' ? cp.value : null)
    setVentas(v.status === 'fulfilled' ? v.value : null)
    setAlbaranes(alb.status === 'fulfilled' ? alb.value.items : [])
    setTareas(rt.status === 'fulfilled' ? rt.value : null)
    // Lo que queda por hacer, con las que tienen fecha primero: es lo que se
    // consulta de un tablero sin abrirlo.
    setProximas(
      lt.status === 'fulfilled'
        ? lt.value
            .filter((t) => t.estado !== 'hecha')
            .sort((a, b) => (a.fecha_limite ?? '9999').localeCompare(b.fecha_limite ?? '9999'))
            .slice(0, 6)
        : [],
    )
    const fallo = [c, cp, v, alb, rt, lt].find((r) => r.status === 'rejected')
    setError(
      fallo && fallo.status === 'rejected'
        ? `Algunos datos no se han podido cargar: ${
            fallo.reason instanceof Error ? fallo.reason.message : 'error desconocido'
          }`
        : null,
    )
    // `refresco` no se usa aquí, pero entra en las dependencias a propósito:
    // es la señal de que hay que volver a pedir los datos.
  }, [obraId, refresco])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const contratado = arbol ? Number(arbol.totales.venta) : 0
  const costePrevisto = arbol ? Number(arbol.totales.coste) : 0
  const certificado = ventas ? Number(ventas.certificado) : 0
  const comprado = compras ? Number(compras.albaranes_total) : 0
  const costeReal = costes ? Number(costes.totales.real_total) : 0
  const margenPrevisto = contratado - costePrevisto

  return (
    <div className="form-section">
      <ErrorNotice error={error} />

      <div className="tarjetas-kpi">
        <Tarjeta
          etiqueta="Contratado (venta)"
          valor={euros(contratado)}
          nota={
            arbol && Number(arbol.totales.venta_anexos) > 0
              ? `${euros(arbol.totales.venta_anexos)} en anexos`
              : 'Solo el contrato principal'
          }
        />
        <Tarjeta
          etiqueta="Certificado a origen"
          valor={euros(certificado)}
          nota={`${certificaciones.length} ${
            certificaciones.length === 1 ? 'certificación' : 'certificaciones'
          }`}
        />
        <Tarjeta
          etiqueta="Coste real"
          valor={euros(costeReal)}
          nota={`Previsto ${euros(costePrevisto)}`}
          alerta={costePrevisto > 0 && costeReal > costePrevisto}
        />
        <Tarjeta
          etiqueta="Margen previsto"
          valor={euros(margenPrevisto)}
          nota={
            contratado > 0
              ? `${((margenPrevisto / contratado) * 100).toFixed(1)} % sobre la venta`
              : undefined
          }
          alerta={margenPrevisto < 0}
        />
        <Tarjeta
          etiqueta="Pendiente de cobro"
          valor={ventas ? euros(ventas.pendiente_de_cobro) : '—'}
          nota={ventas ? `${euros(ventas.cobrado)} cobrado` : 'Sin datos de facturación'}
          alerta={Boolean(ventas && Number(ventas.pendiente_de_cobro) > 0)}
        />
        <Tarjeta
          etiqueta="Pendiente de pago"
          valor={compras ? euros(compras.pendiente_de_pago) : '—'}
          nota={
            compras
              ? compras.albaranes_sin_facturar > 0
                ? `${compras.albaranes_sin_facturar} albaranes sin facturar`
                : 'Todo lo entregado está facturado'
              : 'Sin datos de compras'
          }
          alerta={Boolean(compras && Number(compras.pendiente_de_pago) > 0)}
        />
      </div>

      <div className="medidores">
        <Medidor
          etiqueta="Certificado sobre lo contratado"
          parte={certificado}
          total={contratado}
        />
        <Medidor
          etiqueta="Coste real sobre el previsto"
          parte={costeReal}
          total={costePrevisto}
        />
        <Medidor
          etiqueta="Comprado sobre el coste previsto"
          parte={comprado}
          total={costePrevisto}
          detalle={`${euros(comprado)} en albaranes de ${euros(costePrevisto)}`}
        />
      </div>

      <div className="page-head" style={{ marginTop: 'var(--sp-5)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Desviación por capítulo</h2>
      </div>
      {costes ? (
        <DesviacionPorCapitulo capitulos={costes.capitulos} />
      ) : (
        <EmptyState title="Sin informe de coste">
          El informe de coste real vs. presupuestado no está disponible.
        </EmptyState>
      )}

      {tareas && (tareas.pendientes + tareas.en_curso + tareas.hechas > 0) && (
        <>
          <div className="page-head" style={{ marginTop: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Tareas</h2>
          </div>
          <div className="tareas-widget">
            <div className="tareas-widget__cifras">
              <span className="tareas-widget__cifra">
                <span className="cuadre__etiqueta">Pendientes</span>
                <strong>{tareas.pendientes}</strong>
              </span>
              <span className="tareas-widget__cifra">
                <span className="cuadre__etiqueta">En curso</span>
                <strong>{tareas.en_curso}</strong>
              </span>
              <span className="tareas-widget__cifra">
                <span className="cuadre__etiqueta">Vencidas</span>
                <strong className={tareas.vencidas > 0 ? 'cuadre--ojo' : undefined}>
                  {tareas.vencidas}
                </strong>
              </span>
            </div>
            {proximas.length > 0 && (
              <ul className="tareas-widget__lista">
                {proximas.map((t) => (
                  <li key={t.id} className="tareas-widget__fila">
                    <span>{t.titulo}</span>
                    <span className="muted">
                      {t.fecha_limite ?? 'sin fecha'}
                      {t.responsable_nombre ? ` · ${t.responsable_nombre}` : ''}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}

      {albaranes.length > 0 && (
        <>
          <div className="page-head" style={{ marginTop: 'var(--sp-5)' }}>
            <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Últimas entregas</h2>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Albarán</th>
                  <th>Proveedor</th>
                  <th>Fecha</th>
                  <th className="table__num">Importe</th>
                </tr>
              </thead>
              <tbody>
                {albaranes.map((a) => (
                  <tr key={a.id}>
                    <td>{a.codigo}</td>
                    <td>{a.proveedor_razon_social}</td>
                    <td>{a.fecha}</td>
                    <td className="table__num">{euros(a.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}
