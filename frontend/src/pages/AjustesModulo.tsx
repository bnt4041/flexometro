import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import { EmptyState, ErrorNotice } from '../components/ui'
import { NumeracionCard } from '../components/NumeracionCard'
import { api } from '../lib/api'
import { useWorkspace } from '../workspace'

/** Ajustes propios de un módulo activo (Fase 17), autoservicio del admin de
 *  organización — por ahora solo numeración, un módulo puede sumar más
 *  ajustes en el futuro sin tocar la ruta. */
export function AjustesModulo() {
  const { t } = useTranslation()
  const { codigo = '' } = useParams()
  const { modules } = useWorkspace()
  const [cifsDistintos, setCifsDistintos] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const modulo = modules.find((m) => m.code === codigo)

  const cargarCifsDistintos = useCallback(async () => {
    try {
      setCifsDistintos((await api.ajustes.numeracion()).cifs_distintos)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    }
  }, [t])

  useEffect(() => {
    void cargarCifsDistintos()
  }, [cargarCifsDistintos])

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{t('nav.ajustesDe', { modulo: modulo?.name ?? codigo })}</h1>
          {modulo && <p className="page-lead">{modulo.description}</p>}
        </div>
        <Link className="btn" to="/ajustes">
          <ArrowLeft size={16} aria-hidden="true" />
          {t('ajustes.modulos.volverAAjustes')}
        </Link>
      </div>

      <ErrorNotice error={error} />

      {!modulo ? (
        <EmptyState title={t('ajustes.ajustesDeModulo.moduloNoEncontrado')}>
          {t('ajustes.ajustesDeModulo.moduloNoEncontradoDesc')}
        </EmptyState>
      ) : modulo.tipo_documento_numeracion === null ? (
        <EmptyState title={t('ajustes.ajustesDeModulo.sinAjustesPropios')}>
          {t('ajustes.ajustesDeModulo.sinAjustesPropiosDesc')}
        </EmptyState>
      ) : (
        <NumeracionCard
          cifsDistintos={cifsDistintos}
          soloTipos={[modulo.tipo_documento_numeracion]}
          listar={() => api.ajustes.numeracion().then((r) => r.patrones)}
          actualizar={api.ajustes.actualizarNumeracion}
          incluirTitulo={false}
        />
      )}
    </>
  )
}
