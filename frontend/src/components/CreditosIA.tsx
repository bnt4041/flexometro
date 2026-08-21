import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '../lib/api'
import type { CreditosIA as CreditosIATipo } from '../lib/api'

/** Medidor de "créditos IA" (Fase 38) del mes en curso — unidad propia que
 *  sustituye a hablar de tokens de DeepSeek/Gemini por separado (precios muy
 *  distintos entre sí, ver `app/modules/core/creditos_service.py`). Se
 *  oculta sola si la cuenta no tiene tarifa asignada: no hay cuota que
 *  mostrar, y "0 de 0" confundiría más de lo que informa. */
export function CreditosIA() {
  const { t } = useTranslation()
  const [datos, setDatos] = useState<CreditosIATipo | null>(null)

  useEffect(() => {
    let cancelado = false
    api.creditosIA
      .get()
      .then((d) => {
        if (!cancelado) setDatos(d)
      })
      .catch(() => {
        /* silencioso: es un widget informativo, no bloquea nada si falla */
      })
    return () => {
      cancelado = true
    }
  }, [])

  if (!datos || datos.sin_tarifa) return null

  const pct = datos.incluidos > 0 ? Math.min(100, (datos.consumidos / datos.incluidos) * 100) : 0
  const sobrepasado = datos.consumidos > datos.incluidos

  return (
    <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
      <div className="module-row__title">{t('ajustes.creditosIA.titulo')}</div>
      <div className="module-row__desc" style={{ marginBottom: 'var(--sp-3)' }}>
        {t('ajustes.creditosIA.descripcion', {
          consumidos: datos.consumidos.toLocaleString('es-ES'),
          incluidos: datos.incluidos.toLocaleString('es-ES'),
        })}
      </div>
      <div className="creditos-ia__barra">
        <div
          className={`creditos-ia__relleno${sobrepasado ? ' creditos-ia__relleno--exceso' : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {sobrepasado && (
        <p className="muted" style={{ marginTop: 'var(--sp-2)', fontSize: 'var(--fs-xs)' }}>
          {t('ajustes.creditosIA.sobrepasado')}
        </p>
      )}
    </div>
  )
}
