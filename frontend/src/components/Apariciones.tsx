import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Icon } from './Icon'
import { EmptyState, ErrorNotice } from './ui'
import {
  ETIQUETA_ESTADO,
  ETIQUETA_ESTADO_ALBARAN,
  ETIQUETA_ESTADO_CERTIFICACION,
  ETIQUETA_ESTADO_FACTURA,
  ETIQUETA_ESTADO_OBRA,
} from '../lib/api'
import type { Aparicion, TipoAparicion } from '../lib/api'

const ETIQUETA_TIPO: Record<TipoAparicion, string> = {
  presupuesto: 'Presupuesto',
  obra: 'Obra',
  albaran: 'Albarán',
  factura: 'Factura',
  concepto: 'Banco de precios',
  certificacion: 'Certificación',
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
}

const RUTA_TIPO: Record<TipoAparicion, (id: string) => string> = {
  presupuesto: (id) => `/presupuestos/${id}`,
  obra: (id) => `/obras/${id}`,
  albaran: (id) => `/albaranes/${id}`,
  factura: (id) => `/facturas/${id}`,
  concepto: (id) => `/banco-precios/${id}`,
  certificacion: (id) => `/certificaciones/${id}`,
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
    default:
      return a.estado
  }
}

// La certificación usa un prefijo de clase distinto (`chip--estado-cert-*`)
// para no compartir color con el "borrador"/"emitida" de presupuesto y
// factura, que significan otra cosa — ver `CertificacionDetalle.tsx`.
function claseEstado(a: Aparicion): string {
  return a.tipo === 'certificacion' ? `chip--estado-cert-${a.estado}` : `chip--estado-${a.estado}`
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
          En cuanto se use en un presupuesto, obra, albarán, factura, certificación o tarifa del
          banco de precios, aparecerá aquí.
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
