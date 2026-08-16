import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, useLocation } from 'react-router-dom'

import logoOscuro from '../assets/logo-sobre-oscuro.png'
import { useWorkspace } from '../workspace'

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const { principal, modules, salir, cambiarOrganizacion } = useWorkspace()
  const active = modules.filter((m) => m.is_active && m.nav.length > 0)
  const varias = (principal?.organizaciones.length ?? 0) > 1
  const esSuperadmin = principal?.roles.includes('superadmin') ?? false
  const esAdminOrganizacion =
    (principal?.roles.includes('admin') ?? false) && principal?.organization_id != null

  // El menú es un cajón que se superpone en pantallas estrechas (no reduce el
  // ancho del contenido), y una barra lateral fija a partir de la anchura de
  // tableta — mismo patrón que cualquier panel responsive convencional.
  const [menuAbierto, setMenuAbierto] = useState(false)
  const location = useLocation()
  useEffect(() => {
    setMenuAbierto(false)
  }, [location.pathname])

  // En escritorio la barra lateral se puede recoger si se desea, para ganar
  // ancho de contenido; se recuerda entre sesiones.
  const [colapsada, setColapsada] = useState(
    () => localStorage.getItem('obrai:sidebar-colapsada') === '1',
  )
  useEffect(() => {
    localStorage.setItem('obrai:sidebar-colapsada', colapsada ? '1' : '0')
  }, [colapsada])

  const clasesShell = ['shell', menuAbierto && 'shell--menu-abierto', colapsada && 'shell--sidebar-colapsada']
    .filter(Boolean)
    .join(' ')

  return (
    <div className={clasesShell}>
      {menuAbierto && (
        <div className="sidebar-backdrop" onClick={() => setMenuAbierto(false)} />
      )}

      <aside className="sidebar" aria-hidden={colapsada}>
        <div className="brand">
          <img src={logoOscuro} alt="Flexómetro" className="brand__mark" />
        </div>
        <nav className="nav">
          {active.map((module) => (
            <div key={module.code}>
              <div className="nav__group-label">
                {module.name}
                {esAdminOrganizacion && module.tipo_documento_numeracion !== null && (
                  <NavLink
                    to={`/ajustes/modulo/${module.code}`}
                    className="nav__group-ajustes"
                    aria-label={t('nav.ajustesDe', { modulo: module.name })}
                    title={t('nav.ajustesDe', { modulo: module.name })}
                  >
                    ⚙️
                  </NavLink>
                )}
              </div>
              {module.nav.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    isActive ? 'nav__link nav__link--active' : 'nav__link'
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}

          {esAdminOrganizacion && (
            <div>
              <div className="nav__group-label">{t('nav.grupoOrganizacion')}</div>
              <NavLink
                to="/usuarios-grupos"
                className={({ isActive }) =>
                  isActive ? 'nav__link nav__link--active' : 'nav__link'
                }
              >
                {t('nav.usuariosYGrupos')}
              </NavLink>
            </div>
          )}

          {esSuperadmin && (
            <div>
              <div className="nav__group-label">{t('nav.grupoAdministracion')}</div>
              <NavLink
                to="/admin/cuentas"
                className={({ isActive }) =>
                  isActive || location.pathname.startsWith('/admin/organizaciones')
                    ? 'nav__link nav__link--active'
                    : 'nav__link'
                }
              >
                {t('nav.cuentas')}
              </NavLink>
              <NavLink
                to="/admin/tarifas"
                className={({ isActive }) =>
                  isActive ? 'nav__link nav__link--active' : 'nav__link'
                }
              >
                {t('nav.tarifas')}
              </NavLink>
              <NavLink
                to="/admin/personal-plataforma"
                className={({ isActive }) =>
                  isActive ? 'nav__link nav__link--active' : 'nav__link'
                }
              >
                {t('nav.personalPlataforma')}
              </NavLink>
              <NavLink
                to="/admin/ajustes"
                className={({ isActive }) =>
                  isActive ? 'nav__link nav__link--active' : 'nav__link'
                }
              >
                {t('nav.ajustes')}
              </NavLink>
            </div>
          )}
        </nav>
      </aside>

      <div className="main">
        <header className="topbar">
          <button
            type="button"
            className="topbar__menu-btn"
            aria-label={t('nav.abrirMenu')}
            aria-expanded={menuAbierto}
            onClick={() => setMenuAbierto((v) => !v)}
          >
            <span />
            <span />
            <span />
          </button>

          <button
            type="button"
            className="topbar__colapsar-btn"
            aria-label={colapsada ? t('nav.mostrarMenu') : t('nav.ocultarMenu')}
            aria-expanded={!colapsada}
            onClick={() => setColapsada((v) => !v)}
          >
            {colapsada ? '›' : '‹'}
          </button>

          <div className="topbar__org">
            {varias ? (
              <select
                className="select"
                style={{ width: 'auto' }}
                value={principal!.organization_slug ?? ''}
                onChange={(e) => void cambiarOrganizacion(e.target.value)}
              >
                {principal!.organizaciones.map((slug) => (
                  <option key={slug} value={slug}>
                    {slug}
                  </option>
                ))}
              </select>
            ) : (
              <span className="topbar__org-name">
                {principal?.organization_slug ?? t('nav.plataforma')}
              </span>
            )}
          </div>

          <div className="topbar__usuario">
            <span className="muted topbar__usuario-nombre">{principal?.username ?? 'sin sesión'}</span>
            {principal?.roles.includes('admin') && <span className="badge">admin</span>}
            <button className="btn btn--sm" onClick={salir}>
              {t('nav.salir')}
            </button>
          </div>
        </header>
        <main className="content">
          <div className="content__inner">{children}</div>
        </main>
      </div>
    </div>
  )
}
