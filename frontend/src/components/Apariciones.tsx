import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Icon } from './Icon'
import { EmptyState, ErrorNotice } from './ui'
import {
  ETIQUETA_ESTADO,
  ETIQUETA_ESTADO_ALBARAN,
  ETIQUETA_ESTADO_CERTIFICACION,
  ETIQUETA_ESTADO_CONTRATO,
  ETIQUETA_ESTADO_FACTURA,
  ETIQUETA_ESTADO_FACTURA_RECIBIDA,
  ETIQUETA_ESTADO_OBRA,
  ETIQUETA_ESTADO_PEDIDO,
} from '../lib/api'
import type { Aparicion, TipoAparicion } from '../lib/api'

const ETIQUETA_TIPO: Record<TipoAparicion, string> = {
  presupuesto: 'Presupuesto',
  obra: 'Obra',
  albaran: 'Albarán',
  factura: 'Factura',
  concepto: 'Banco de precios',
  certificacion: 'Certificación',
  pedido: 'Pedido',
  contrato: 'Contrato',
  factura_recibida: 'Factura recibida',
}

// Mismo icono que usa cada módulo en su propia navegación (ver `nav` de
// cada `ModuleSpec` en el backend) — así una fila se reconoce de un vistazo
// aunque la lista mezcle tipos.
const ICONO_TIPO: Record<TipoAparicion, string> = {
  presupuesto: 'calculator',
  obra: 'hard-hat',
  albaran: 'truck',
  factura: 'receipt',
  concepto: 'layers',
  certificacion: 'clipboard-check',
  pedido: 'truck',
  contrato: 'file-text',
  factura_recibida: 'receipt',
}

const RUTA_TIPO: Record<TipoAparicion, (id: string) => string> = {
  presupuesto: (id) => `/presupuestos/${id}`,
  obra: (id) => `/obras/${id}`,
  albaran: (id) => `/albaranes/${id}`,
  factura: (id) => `/facturas/${id}`,
  concepto: (id) => `/banco-precios/${id}`,
  certificacion: (id) => `/certificaciones/${id}`,
  pedido: (id) => `/pedidos/${id}`,
  contrato: (id) => `/contratos/${id}`,
  factura_recibida: (id) => `/facturas-recibidas/${id}`,
}

function etiquetaEstado(a: Aparicion): string | null {
  if (!a.estado) return null
  switch (a.tipo) {
    case 'presupuesto':
      return ETIQUETA_ESTADO[a.estado as keyof typeof ETIQUETA_ESTADO] ?? a.estado
    case 'obra':
      return ETIQUETA_ESTADO_OBRA[a.estado as keyof typeof ETIQUETA_ESTADO_OBRA] ?? a.estado
    case 'albaran':
      return ETIQUETA_ESTADO_ALBARAN[a.estado as keyof typeof ETIQUETA_ESTADO_ALBARAN] ?? a.estado
    case 'factura':
      return ETIQUETA_ESTADO_FACTURA[a.estado as keyof typeof ETIQUETA_ESTADO_FACTURA] ?? a.estado
    case 'certificacion':
      return (
        ETIQUETA_ESTADO_CERTIFICACION[a.estado as keyof typeof ETIQUETA_ESTADO_CERTIFICACION] ??
        a.estado
      )
    case 'pedido':
      return ETIQUETA_ESTADO_PEDIDO[a.estado as keyof typeof ETIQUETA_ESTADO_PEDIDO] ?? a.estado
    case 'contrato':
      return ETIQUETA_ESTADO_CONTRATO[a.estado as keyof typeof ETIQUETA_ESTADO_CONTRATO] ?? a.estado
    case 'factura_recibida':
      return (
        ETIQUETA_ESTADO_FACTURA_RECIBIDA[a.estado as keyof typeof ETIQUETA_ESTADO_FACTURA_RECIBIDA] ??
        a.estado
      )
    default:
      return a.estado
  }
}

// Cada tipo con estado propio usa su propio prefijo de clase (`chip--estado-
// cert-*`, `chip--estado-pedido-*`...) para no compartir color entre
// entidades donde el mismo valor ("borrador", "pendiente"...) significa otra
// cosa — ver los `Detalle.tsx` de cada una.
const PREFIJO_CLASE_ESTADO: Partial<Record<TipoAparicion, string>> = {
  certificacion: 'chip--estado-cert-',
  pedido: 'chip--estado-pedido-',
  contrato: 'chip--estado-contrato-',
  factura_recibida: 'chip--estado-fr-',
}

function claseEstado(a: Aparicion): string {
  return `${PREFIJO_CLASE_ESTADO[a.tipo] ?? 'chip--estado-'}${a.estado}`
}

/** Pestaña "Apariciones" de una ficha (Tercero, Fase 46; Contacto, Fase 49):
 *  en qué presupuestos/obras/albaranes/facturas/certificaciones/tarifas del
 *  banco de precios aparece. Solo lectura — para ir directo a la ficha real
 *  se pincha la fila. Recibe la función de carga en vez de un id — a
 *  diferencia de Notas/Documentos, cada entidad tiene su propia consulta de
 *  apariciones (ver `Historial`, mismo motivo). */
export function Apariciones({ cargar: cargarFilas }: { cargar: () => Promise<Aparicion[]> }) {
  const [filas, setFilas] = useState<Aparicion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      setFilas(await cargarFilas())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  if (cargando) return null

  return (
    <>
      <ErrorNotice error={error} />

      {filas.length === 0 ? (
        <EmptyState title="No aparece en ninguna ficha todavía">
          En cuanto se use en un presupuesto, obra, pedido, contrato, albarán, factura (recibida o
          emitida), certificación o tarifa del banco de precios, aparecerá aquí.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Tipo</th>
                <th>Código</th>
                <th>Título</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {filas.map((a) => (
                <tr key={`${a.tipo}-${a.id}`}>
                  <td>
                    <Link className="btn btn--sm" to={RUTA_TIPO[a.tipo](a.id)}>
                      <Icon name={ICONO_TIPO[a.tipo]} />
                      {ETIQUETA_TIPO[a.tipo]}
                    </Link>
                  </td>
                  <td className="table__code">{a.codigo}</td>
                  <td>
                    {a.titulo}
                    {a.subtitulo && <div className="muted">{a.subtitulo}</div>}
                  </td>
                  <td>
                    {etiquetaEstado(a) && (
                      <span className={`chip ${claseEstado(a)}`}>{etiquetaEstado(a)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
