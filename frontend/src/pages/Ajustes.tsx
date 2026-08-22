import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { ArrowRight, Settings } from 'lucide-react'

import { CreditosIA } from '../components/CreditosIA'
import { useWorkspace } from '../workspace'

/** Vestíbulo de Ajustes (Fase 17): desde aquí se llega a la activación de
 *  módulos (abierta a cualquier usuario, como ya era) y, si el principal es
 *  admin de su organización, a los ajustes propios de cada módulo activo
 *  (numeración, por ahora), al diccionario y a la traducción — el mismo
 *  destino al que llevan las ruedas dentadas de la barra lateral. */
export function Ajustes() {
  const { t } = useTranslation()
  const { principal, modules } = useWorkspace()
  const esAdminOrganizacion =
    (principal?.roles.includes('admin') ?? false) && principal?.organization_id != null
  const modulosConAjustes = modules.filter(
    (m) => m.is_active && m.tipo_documento_numeracion !== null,
  )

  return (
    <>
      <h1 className="page-title">{t('ajustes.titulo')}</h1>
      <p className="page-lead">{t('ajustes.descripcion')}</p>

      <CreditosIA />

      <div className="card" style={{ marginBottom: 'var(--sp-5)' }}>
        <div className="module-row">
          <div>
            <div className="module-row__title">{t('ajustes.modulos.titulo')}</div>
            <div className="module-row__desc">{t('ajustes.modulos.descripcionHub')}</div>
          </div>
          <Link className="btn" to="/ajustes/modulos">
            {t('comun.abrir')}
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </div>
        {esAdminOrganizacion && (
          <>
            <div className="module-row">
              <div>
                <div className="module-row__title">Empresa</div>
                <div className="module-row__desc">
                  Datos básicos y logo de la organización, para documentos y plantillas.
                </div>
              </div>
              <Link className="btn" to="/ajustes/empresa">
                {t('comun.abrir')}
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <div className="module-row">
              <div>
                <div className="module-row__title">{t('ajustes.diccionario.titulo')}</div>
                <div className="module-row__desc">{t('ajustes.diccionario.descripcionHub')}</div>
              </div>
              <Link className="btn" to="/ajustes/diccionario">
                {t('comun.abrir')}
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <div className="module-row">
              <div>
                <div className="module-row__title">{t('ajustes.traduccion.titulo')}</div>
                <div className="module-row__desc">{t('ajustes.traduccion.descripcionHub')}</div>
              </div>
              <Link className="btn" to="/ajustes/traduccion">
                {t('comun.abrir')}
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <div className="module-row">
              <div>
                <div className="module-row__title">{t('ajustes.camposLibres.titulo')}</div>
                <div className="module-row__desc">{t('ajustes.camposLibres.descripcionHub')}</div>
              </div>
              <Link className="btn" to="/ajustes/campos-libres">
                {t('comun.abrir')}
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
            <div className="module-row">
              <div>
                <div className="module-row__title">Monedas</div>
                <div className="module-row__desc">
                  Tipo de cambio de referencia, solo para consulta.
                </div>
              </div>
              <Link className="btn" to="/ajustes/monedas">
                {t('comun.abrir')}
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </div>
          </>
        )}
      </div>

      {esAdminOrganizacion && modulosConAjustes.length > 0 && (
        <>
          <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, margin: '0 0 var(--sp-3)' }}>
            {t('ajustes.ajustesDeModulo.titulo')}
          </h2>
          <div className="card">
            {modulosConAjustes.map((m) => (
              <div className="module-row" key={m.code}>
                <div>
                  <div className="module-row__title">{m.name}</div>
                  <div className="module-row__desc">{m.description}</div>
                </div>
                <Link
                  className="btn"
                  to={`/ajustes/modulo/${m.code}`}
                  aria-label={t('nav.ajustesDe', { modulo: m.name })}
                >
                  <Settings size={14} aria-hidden="true" /> {t('nav.ajustes')}
                </Link>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  )
}
