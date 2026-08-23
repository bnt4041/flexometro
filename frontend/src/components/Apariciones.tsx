import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Icon } from './Icon'
import { EmptyState, ErrorNotice } from './ui'
import {
  ETIQUETA_ESTADO,
  ETIQUETA_ESTADO_ALBARAN,
  ETIQUETA_ESTADO_FACTURA,
  ETIQUETA_ESTADO_OBRA,
  api,
} from '../lib/api'
import type { Aparicion, TipoAparicion } from '../lib/api'

const ETIQUETA_TIPO: Record<TipoAparicion, string> = {
  presupuesto: 'Presupuesto',
  obra: 'Obra',
  albaran: 'Albarán',
  factura: 'Factura',
  concepto: 'Banco de precios',
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
}

const RUTA_TIPO: Record<TipoAparicion, (id: string) => string> = {
  presupuesto: (id) => `/presupuestos/${id}`,
  obra: (id) => `/obras/${id}`,
  albaran: (id) => `/albaranes/${id}`,
  factura: (id) => `/facturas/${id}`,
  concepto: (id) => `/banco-precios/${id}`,
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
    default:
      return a.estado
  }
}

/** Pestaña "Apariciones" (Fase 46) de la ficha de un tercero: en qué
 *  presupuestos es cliente, en qué obras (heredado del presupuesto), en qué
 *  albaranes es proveedor, qué facturas tiene y en qué tarifas del banco de
 *  precios aparece como suministrador. Solo lectura — para ir directo a la
 *  ficha real se pincha la fila. */
export function Apariciones({ terceroId }: { terceroId: string }) {
  const [filas, setFilas] = useState<Aparicion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      setFilas(await api.terceros.apariciones(terceroId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [terceroId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  if (cargando) return null

  return (
    <>
      <ErrorNotice error={error} />

      {filas.length === 0 ? (
        <EmptyState title="No aparece en ninguna ficha todavía">
          En cuanto se use como cliente o proveedor en un presupuesto, obra, albarán, factura o
          tarifa del banco de precios, aparecerá aquí.
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
                      <span className={`chip chip--estado-${a.estado}`}>{etiquetaEstado(a)}</span>
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
