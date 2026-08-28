import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState, ErrorNotice, formatoImporte } from './ui'
import {
  ETIQUETA_ESTADO_ALBARAN,
  ETIQUETA_ESTADO_CERTIFICACION,
  ETIQUETA_ESTADO_CONTRATO,
  ETIQUETA_ESTADO_FACTURA,
  ETIQUETA_ESTADO_FACTURA_RECIBIDA,
  ETIQUETA_ESTADO_PEDIDO,
  api,
} from '../lib/api'

export interface NodoTrazabilidad {
  tipo:
    | 'presupuesto'
    | 'pedido'
    | 'contrato'
    | 'albaran'
    | 'factura-recibida'
    | 'certificacion'
    | 'factura'
    | 'solicitud-precios'
    | 'obra'
    | 'tercero'
  etiqueta: string
  ruta: string
  fecha?: string | null
  estadoEtiqueta?: string | null
  importe?: string | null
}

const ETIQUETA_TIPO: Record<NodoTrazabilidad['tipo'], string> = {
  presupuesto: 'Presupuesto',
  pedido: 'Pedido',
  contrato: 'Contrato',
  albaran: 'Albarán',
  'factura-recibida': 'Factura recibida',
  certificacion: 'Certificación',
  factura: 'Factura',
  'solicitud-precios': 'Solicitud de precios',
  obra: 'Obra',
  tercero: 'Tercero',
}

function Fila({ nodo }: { nodo: NodoTrazabilidad }) {
  return (
    <div className="trazabilidad__fila">
      <span className="chip chip--traza">{ETIQUETA_TIPO[nodo.tipo]}</span>
      <Link className="table__link trazabilidad__enlace" to={nodo.ruta}>
        {nodo.etiqueta}
      </Link>
      {nodo.estadoEtiqueta && <span className="muted">{nodo.estadoEtiqueta}</span>}
      {nodo.fecha && <span className="muted">{nodo.fecha}</span>}
      {nodo.importe && <span className="trazabilidad__importe">{formatoImporte(nodo.importe)} €</span>}
    </div>
  )
}

/** Pestaña "Trazabilidad": de dónde viene un documento y qué otros
 *  documentos están enlazados a él — el seguimiento, no la auditoría (eso ya
 *  lo cubre "Historial"). Sin backend propio: `origen` lo arma quien monta
 *  la pestaña con las FK que su propia ficha ya tiene cargadas, y
 *  `cargarAsociados` orquesta los listados de cada módulo filtrados por
 *  `obra_id` — mismo patrón que ya usan `ComprasObra`/`VentasObra` dentro de
 *  la ficha de obra. */
export function Trazabilidad({
  origen,
  cargarAsociados,
}: {
  origen: NodoTrazabilidad[]
  cargarAsociados?: () => Promise<NodoTrazabilidad[]>
}) {
  const [asociados, setAsociados] = useState<NodoTrazabilidad[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(Boolean(cargarAsociados))

  const recargar = useCallback(async () => {
    if (!cargarAsociados) return
    setCargando(true)
    try {
      const nodos = [...(await cargarAsociados())]
      nodos.sort((a, b) => (b.fecha ?? '').localeCompare(a.fecha ?? ''))
      setAsociados(nodos)
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

  return (
    <div className="trazabilidad">
      <section>
        <h2 className="trazabilidad__titulo">De dónde viene</h2>
        {origen.length === 0 ? (
          <p className="muted">Se creó directo, sin partir de otro documento.</p>
        ) : (
          <div className="trazabilidad__lista">
            {origen.map((n) => (
              <Fila key={`${n.tipo}-${n.ruta}`} nodo={n} />
            ))}
          </div>
        )}
      </section>

      {cargarAsociados !== undefined && (
        <section style={{ marginTop: 'var(--sp-5)' }}>
          <h2 className="trazabilidad__titulo">Objetos asociados a esta obra</h2>
          <ErrorNotice error={error} />
          {cargando ? null : !asociados || asociados.length === 0 ? (
            <EmptyState title="Sin más documentos en esta obra" />
          ) : (
            <div className="trazabilidad__lista">
              {asociados.map((n) => (
                <Fila key={`${n.tipo}-${n.ruta}`} nodo={n} />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  )
}

/** Todo lo que cuelga de una obra, de los 7 tipos de documento, orquestado
 *  en el navegador — mismo patrón que ya usan `ComprasObra`/`VentasObra`
 *  dentro de la ficha de la obra: cada módulo ya expone su propio listado
 *  filtrado por `obra_id`, así que no hace falta ningún endpoint nuevo.
 *  `excluir` quita el propio documento que abrió la pestaña (que también
 *  aparecería si no se filtrara: es de la misma obra que él mismo). */
export async function cargarAsociadosDeObra(
  obraId: string,
  excluir?: { tipo: NodoTrazabilidad['tipo']; id: string },
  // Para la propia ficha de la obra: sus presupuestos vinculados ya se
  // enseñan en "de dónde viene" (son el origen, no solo algo asociado), así
  // que no hace falta repetirlos aquí también.
  omitirTipo?: NodoTrazabilidad['tipo'],
): Promise<NodoTrazabilidad[]> {
  const fuera = (tipo: NodoTrazabilidad['tipo'], id: string) =>
    excluir?.tipo === tipo && excluir.id === id

  const [presupuestos, pedidos, contratos, albaranes, facturasRecibidas, certificaciones, facturas] =
    await Promise.allSettled([
      api.obras.presupuestos(obraId),
      api.pedidos.list({ obra_id: obraId, limit: 200 }),
      api.contratos.list({ obra_id: obraId, limit: 200 }),
      api.albaranes.list({ obra_id: obraId, limit: 200 }),
      api.facturasRecibidas.list({ obra_id: obraId, limit: 200 }),
      api.certificaciones.list({ obra_id: obraId, limit: 200 }),
      api.facturas.list({ obra_id: obraId, limit: 200 }),
    ])

  const nodos: NodoTrazabilidad[] = []

  if (presupuestos.status === 'fulfilled' && omitirTipo !== 'presupuesto') {
    for (const v of presupuestos.value) {
      if (fuera('presupuesto', v.presupuesto_id)) continue
      nodos.push({
        tipo: 'presupuesto',
        etiqueta: `${v.presupuesto_codigo} · ${v.presupuesto_nombre}`,
        ruta: `/presupuestos/${v.presupuesto_id}`,
        fecha: v.fecha_vinculacion,
        estadoEtiqueta: v.tipo === 'principal' ? 'Principal' : 'Anexo',
      })
    }
  }
  if (pedidos.status === 'fulfilled') {
    for (const p of pedidos.value.items) {
      if (fuera('pedido', p.id)) continue
      nodos.push({
        tipo: 'pedido',
        etiqueta: `${p.codigo} · ${p.tercero_razon_social}`,
        ruta: `/pedidos/${p.id}`,
        fecha: p.fecha,
        estadoEtiqueta: ETIQUETA_ESTADO_PEDIDO[p.estado],
        importe: p.total,
      })
    }
  }
  if (contratos.status === 'fulfilled') {
    for (const c of contratos.value.items) {
      if (fuera('contrato', c.id)) continue
      nodos.push({
        tipo: 'contrato',
        etiqueta: `${c.codigo} · ${c.tercero_razon_social}`,
        ruta: `/contratos/${c.id}`,
        fecha: c.fecha_firma,
        estadoEtiqueta: ETIQUETA_ESTADO_CONTRATO[c.estado],
        importe: c.importe,
      })
    }
  }
  if (albaranes.status === 'fulfilled') {
    for (const a of albaranes.value.items) {
      if (fuera('albaran', a.id)) continue
      nodos.push({
        tipo: 'albaran',
        etiqueta: `${a.codigo} · ${a.tercero_razon_social}`,
        ruta: `/albaranes/${a.id}`,
        fecha: a.fecha,
        estadoEtiqueta: ETIQUETA_ESTADO_ALBARAN[a.estado],
        importe: a.total,
      })
    }
  }
  if (facturasRecibidas.status === 'fulfilled') {
    for (const f of facturasRecibidas.value.items) {
      if (fuera('factura-recibida', f.id)) continue
      nodos.push({
        tipo: 'factura-recibida',
        etiqueta: `${f.codigo} · ${f.proveedor_razon_social}`,
        ruta: `/facturas-recibidas/${f.id}`,
        fecha: f.fecha,
        estadoEtiqueta: ETIQUETA_ESTADO_FACTURA_RECIBIDA[f.estado],
        importe: f.total,
      })
    }
  }
  if (certificaciones.status === 'fulfilled') {
    for (const c of certificaciones.value.items) {
      if (fuera('certificacion', c.id)) continue
      nodos.push({
        tipo: 'certificacion',
        etiqueta: `Certificación nº ${c.numero} · ${c.codigo}`,
        ruta: `/certificaciones/${c.id}`,
        fecha: c.fecha,
        estadoEtiqueta: ETIQUETA_ESTADO_CERTIFICACION[c.estado],
      })
    }
  }
  if (facturas.status === 'fulfilled') {
    for (const f of facturas.value.items) {
      if (fuera('factura', f.id)) continue
      nodos.push({
        tipo: 'factura',
        etiqueta: `${f.codigo} · ${f.cliente_razon_social}`,
        ruta: `/facturas/${f.id}`,
        fecha: f.fecha_emision,
        estadoEtiqueta: ETIQUETA_ESTADO_FACTURA[f.estado],
        importe: f.total,
      })
    }
  }

  return nodos
}

/** Presupuesto no tiene `obra_id` propio (la FK va al revés, `Obra.presupuesto_id`
 *  / `ObraPresupuesto`) — para su pestaña de Trazabilidad hace falta encontrar
 *  primero la obra que lo usa. Solo resuelve el vínculo PRINCIPAL (el más
 *  común, uno por presupuesto salvo que además sea anexo de otra obra), no
 *  todos los `ObraPresupuesto` posibles — una limitación conocida, no un
 *  listado exhaustivo. */
export async function obraDePresupuesto(presupuestoId: string): Promise<string | null> {
  const pagina = await api.obras.list({ limit: 500 })
  const obra = pagina.items.find((o) => o.presupuesto_id === presupuestoId)
  return obra?.id ?? null
}
