import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, useLocation } from 'react-router-dom'
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Menu,
  Receipt,
  Settings,
  Shield,
  UserCog,
  Users,
} from 'lucide-react'

import logoOscuro from '../assets/logo-sobre-oscuro.png'
import { Icon } from '../components/Icon'
import { Tooltip } from '../components/ui'
import { useSidebarColapsada } from '../lib/sidebarColapsada'
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
  // ancho de contenido; se recuerda entre sesiones. Compartido con
  // `ModalPantalla`, que necesita el mismo interruptor (ver `sidebarColapsada.ts`).
  const [colapsada, alternarColapsada] = useSidebarColapsada()

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
                  <Tooltip texto={t('nav.ajustesDe', { modulo: module.name })}>
                    <NavLink
                      to={`/ajustes/modulo/${module.code}`}
                      className="nav__group-ajustes"
                      aria-label={t('nav.ajustesDe', { modulo: module.name })}
                    >
                      <Settings size={14} aria-hidden="true" />
                    </NavLink>
                  </Tooltip>
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
                  <Icon name={item.icon} />
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
                <UserCog size={16} aria-hidden="true" />
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
                <Building2 size={16} aria-hidden="true" />
                {t('nav.cuentas')}
              </NavLink>
              <NavLink
                to="/admin/tarifas"
                className={({ isActive }) =>
                  isActive ? 'nav__link nav__link--active' : 'nav__link'
                }
              >
                <Receipt size={16} aria-hidden="true" />
                {t('nav.tarifas')}
              </NavLink>
              <NavLink
                to="/admin/personal-plataforma"
                className={({ isActive }) =>
                  isActive ? 'nav__link nav__link--active' : 'nav__link'
                }
              >
                <Users size={16} aria-hidden="true" />
                {t('nav.personalPlataforma')}
              </NavLink>
              <NavLink
                to="/admin/ajustes"
                className={({ isActive }) =>
                  isActive ? 'nav__link nav__link--active' : 'nav__link'
                }
              >
                <Shield size={16} aria-hidden="true" />
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
            <Menu size={20} aria-hidden="true" />
          </button>

          <Tooltip texto={colapsada ? t('nav.mostrarMenu') : t('nav.ocultarMenu')}>
            <button
              type="button"
              className="topbar__colapsar-btn"
              aria-label={colapsada ? t('nav.mostrarMenu') : t('nav.ocultarMenu')}
              aria-expanded={!colapsada}
              onClick={alternarColapsada}
            >
              {colapsada ? (
                <ChevronRight size={16} aria-hidden="true" />
              ) : (
                <ChevronLeft size={16} aria-hidden="true" />
              )}
            </button>
          </Tooltip>

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
            <Tooltip texto={t('nav.salir')}>
              <button className="btn btn--sm" onClick={salir}>
                <LogOut size={14} aria-hidden="true" />
                {t('nav.salir')}
              </button>
            </Tooltip>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
    </div>
  )
}
