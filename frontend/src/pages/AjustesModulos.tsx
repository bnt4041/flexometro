import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ArrowLeft, Power } from 'lucide-react'

import { api } from '../lib/api'
import { useWorkspace } from '../workspace'

export function AjustesModulos() {
  const { t } = useTranslation()
  const { modules, reload } = useWorkspace()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function toggle(code: string, active: boolean) {
    setBusy(code)
    setError(null)
    try {
      await api.setModuleActive(code, active)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('comun.errorDesconocido'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{t('ajustes.modulos.titulo')}</h1>
          <p className="page-lead">{t('ajustes.modulos.descripcionPantalla')}</p>
        </div>
        <Link className="btn" to="/ajustes">
          <ArrowLeft size={16} aria-hidden="true" />
          {t('ajustes.modulos.volverAAjustes')}
        </Link>
      </div>

      {error && <div className="notice notice--error">{error}</div>}

      <div className="card">
        {modules.map((module) => (
          <div className="module-row" key={module.code}>
            <div>
              <div className="module-row__title">
                {module.name}
                {module.always_active && (
                  <span className="badge badge--core">{t('ajustes.modulos.nucleo')}</span>
                )}
              </div>
              <div className="module-row__desc">{module.description}</div>
              {module.depends_on.length > 0 && (
                <div className="module-row__deps">
                  {t('ajustes.modulos.requiere', { modulos: module.depends_on.join(', ') })}
                </div>
              )}
            </div>
            <button
              className={module.is_active ? 'btn' : 'btn btn--primary'}
              disabled={module.always_active || busy !== null}
              onClick={() => void toggle(module.code, !module.is_active)}
            >
              {busy !== module.code && !module.always_active && (
                <Power size={14} aria-hidden="true" />
              )}
              {busy === module.code
                ? '...'
                : module.always_active
                  ? t('ajustes.modulos.siempreActivo')
                  : module.is_active
                    ? t('ajustes.modulos.desactivar')
                    : t('ajustes.modulos.activar')}
            </button>
          </div>
        ))}
      </div>
    </>
  )
}
