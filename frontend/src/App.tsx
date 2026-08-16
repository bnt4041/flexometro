import type { ComponentType, ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import logo from './assets/logo.png'
import { AdminAjustesGlobales } from './pages/AdminAjustesGlobales'
import { AdminCuentaCrear, AdminCuentas } from './pages/AdminCuentas'
import { AdminCuentaDetalle } from './pages/AdminCuentaDetalle'
import { AdminOrganizacionDetalle } from './pages/AdminOrganizacionDetalle'
import { AdminPersonalPlataforma, PersonalPlataformaCrear } from './pages/AdminPersonalPlataforma'
import { AdminPersonalPlataformaDetalle } from './pages/AdminPersonalPlataformaDetalle'
import { AdminTarifaDetalle } from './pages/AdminTarifaDetalle'
import { AdminTarifas, TarifaCrear } from './pages/AdminTarifas'
import { AlbaranCrear, Albaranes } from './pages/Albaranes'
import { AlbaranDetalle } from './pages/AlbaranDetalle'
import { Ajustes } from './pages/Ajustes'
import { AjustesCamposLibres } from './pages/AjustesCamposLibres'
import { AjustesDiccionario } from './pages/AjustesDiccionario'
import { AjustesModulo } from './pages/AjustesModulo'
import { AjustesModulos } from './pages/AjustesModulos'
import { AjustesMonedas } from './pages/AjustesMonedas'
import { AjustesTraduccion } from './pages/AjustesTraduccion'
import { Certificaciones } from './pages/Certificaciones'
import { CertificacionDetalle } from './pages/CertificacionDetalle'
import { Comparador } from './pages/Comparador'
import { Contactos } from './pages/Contactos'
import { CosteReal } from './pages/CosteReal'
import { FacturaDetalle } from './pages/FacturaDetalle'
import { Facturas, FacturaSueltaCrear } from './pages/Facturas'
import { IaPatrones } from './pages/IaPatrones'
import { ImportarBC3 } from './pages/ImportarBC3'
import { ObraCrear, Obras } from './pages/Obras'
import { ObraDetalle } from './pages/ObraDetalle'
import { Personal } from './pages/Personal'
import { Placeholder } from './pages/Placeholder'
import { PrecioDetalle } from './pages/PrecioDetalle'
import { ConceptoCrear, Precios } from './pages/Precios'
import { PresupuestoCrear, Presupuestos } from './pages/Presupuestos'
import { PresupuestoDetalle } from './pages/PresupuestoDetalle'
import { ProductoCrear, Productos } from './pages/Productos'
import { ProductoDetalle } from './pages/ProductoDetalle'
import { TerceroCrear, Terceros } from './pages/Terceros'
import { TerceroDetalle } from './pages/TerceroDetalle'
import { UsuariosGrupos } from './pages/UsuariosGrupos'
import { AppShell } from './shell/AppShell'
import { ToastProvider } from './toast'
import { WorkspaceProvider, useWorkspace } from './workspace'

/** Pantallas ya implementadas, indexadas por la ruta que publica el módulo en
 *  su `nav`. Lo que no esté aquí se pinta como hueco con su fase. */
const PANTALLAS: Record<string, ComponentType> = {
  '/ajustes': Ajustes,
  '/terceros': Terceros,
  '/contactos': Contactos,
  '/productos': Productos,
  '/precios': Precios,
  '/presupuestos': Presupuestos,
  '/importar-bc3': ImportarBC3,
  '/obras': Obras,
  '/personal': Personal,
  '/albaranes': Albaranes,
  '/certificaciones': Certificaciones,
  '/facturas': Facturas,
  '/ia/patrones': IaPatrones,
}

/** Alta y detalle de cada listado, como rutas HIJAS de su propio listado: el
 *  listado (`PANTALLAS`) monta un `<Outlet/>` y estas rutas aparecen encima
 *  en el modal gigante, con URL propia (recargable, compartible) en vez de
 *  vivir solo en estado de React. `path` es relativo al padre. */
const MODALES: Record<
  string,
  { path: string; modulo: string; componente: ComponentType }[]
> = {
  '/terceros': [
    { path: 'nuevo', modulo: 'terceros', componente: TerceroCrear },
    { path: ':id', modulo: 'terceros', componente: TerceroDetalle },
  ],
  '/productos': [
    { path: 'nuevo', modulo: 'catalogo', componente: ProductoCrear },
    { path: ':id', modulo: 'catalogo', componente: ProductoDetalle },
  ],
  '/precios': [
    { path: 'nuevo', modulo: 'presupuestos', componente: ConceptoCrear },
    { path: ':id', modulo: 'presupuestos', componente: PrecioDetalle },
  ],
  '/presupuestos': [
    { path: 'nuevo', modulo: 'presupuestos', componente: PresupuestoCrear },
    { path: ':id', modulo: 'presupuestos', componente: PresupuestoDetalle },
  ],
  '/obras': [
    { path: 'nueva', modulo: 'obras', componente: ObraCrear },
    { path: ':id', modulo: 'obras', componente: ObraDetalle },
  ],
  '/albaranes': [
    { path: 'nuevo', modulo: 'compras', componente: AlbaranCrear },
    { path: ':id', modulo: 'compras', componente: AlbaranDetalle },
  ],
  '/certificaciones': [
    // Sin alta propia: una certificación siempre se crea desde la ficha de
    // una obra, nunca desde este listado.
    { path: ':id', modulo: 'facturacion', componente: CertificacionDetalle },
  ],
  '/facturas': [
    { path: 'nueva', modulo: 'facturacion', componente: FacturaSueltaCrear },
    { path: ':id', modulo: 'facturacion', componente: FacturaDetalle },
  ],
}

/** Rutas de detalle que NO son "un registro más" del listado que las
 *  contiene, sino una vista de análisis/comparación aparte (comparar dos
 *  versiones, coste real vs. presupuestado): siguen siendo páginas propias,
 *  no el modal gigante. */
const DETALLES_INDEPENDIENTES: { path: string; modulo: string; componente: ComponentType }[] = [
  {
    path: '/presupuestos/:id/comparar/:otroId',
    modulo: 'presupuestos',
    componente: Comparador,
  },
  // El informe cruza obras + compras + presupuestos y por eso se registra
  // desde el módulo `compras` (ver costes.py en el backend); aquí solo hace
  // falta que la ruta exista cuando compras esté activo.
  { path: '/obras/:id/costes', modulo: 'compras', componente: CosteReal },
]

/** En qué fase se construye cada pantalla que hoy es un hueco. */
const FASE_POR_RUTA: Record<string, string> = {}

function Workspace() {
  const { principal, modules, estado, error, entrar } = useWorkspace()

  if (estado === 'arrancando') {
    return <Portada>Cargando…</Portada>
  }

  if (estado === 'sin-sesion') {
    return (
      <Portada>
        <p style={{ color: 'var(--c-text-muted)', marginBottom: 'var(--sp-5)' }}>
          Necesitas iniciar sesión para entrar.
        </p>
        <button className="btn btn--primary" onClick={() => void entrar()}>
          Iniciar sesión
        </button>
      </Portada>
    )
  }

  if (estado === 'error') {
    return (
      <Portada>
        <div className="notice notice--error">{error}</div>
        <button className="btn" onClick={() => window.location.reload()}>
          Reintentar
        </button>
      </Portada>
    )
  }

  const activos = modules.filter((m) => m.is_active)
  const codigosActivos = new Set(activos.map((m) => m.code))
  const entradas = activos.flatMap((m) => m.nav)
  // La administración de organizaciones no es un módulo de negocio activable:
  // es un rol de Keycloak más, así que su ruta se gestiona aquí y no sale del
  // registro de módulos como el resto del menú.
  const esSuperadmin = principal?.roles.includes('superadmin') ?? false
  // El personal de la plataforma no pertenece a ninguna organización (Fase
  // 13): no tiene módulos de negocio que listar, así que su menú es solo
  // Administración y no puede caer en /ajustes como el resto.
  const inicio = entradas[0]?.path ?? (esSuperadmin ? '/admin/cuentas' : '/ajustes')
  // Autoservicio de usuarios y grupos: mismo rol `admin` que ya desbloqueaba
  // otras pantallas de organización, no un permiso nuevo. Exige organización
  // además del rol: el personal de la plataforma (Fase 13) puede arrastrar
  // `admin` de cuando pertenecía a una, sin organización que administrar.
  const esAdminOrganizacion =
    (principal?.roles.includes('admin') ?? false) && principal?.organization_id != null

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to={inicio} replace />} />

        {entradas.map((item) => {
          const Pantalla = PANTALLAS[item.path]
          const hijos = (MODALES[item.path] ?? []).filter((m) => codigosActivos.has(m.modulo))
          return (
            <Route
              key={item.path}
              path={item.path}
              element={
                Pantalla ? (
                  <Pantalla />
                ) : (
                  <Placeholder
                    title={item.label}
                    phase={FASE_POR_RUTA[item.path] ?? 'fase por determinar'}
                  />
                )
              }
            >
              {hijos.map(({ path, componente: Componente }) => (
                <Route key={path} path={path} element={<Componente />} />
              ))}
            </Route>
          )
        })}

        {DETALLES_INDEPENDIENTES.filter((d) => codigosActivos.has(d.modulo)).map(
          ({ path, componente: Componente }) => (
            <Route key={path} path={path} element={<Componente />} />
          ),
        )}

        <Route path="/ajustes/modulos" element={<AjustesModulos />} />

        {esAdminOrganizacion && (
          <>
            <Route path="/usuarios-grupos" element={<UsuariosGrupos />} />
            <Route path="/ajustes/modulo/:codigo" element={<AjustesModulo />} />
            <Route path="/ajustes/diccionario" element={<AjustesDiccionario />} />
            <Route path="/ajustes/traduccion" element={<AjustesTraduccion />} />
            <Route path="/ajustes/campos-libres" element={<AjustesCamposLibres />} />
            <Route path="/ajustes/monedas" element={<AjustesMonedas />} />
          </>
        )}

        {esSuperadmin && (
          <>
            <Route path="/admin/cuentas" element={<AdminCuentas />}>
              <Route path="nueva" element={<AdminCuentaCrear />} />
              <Route path=":id" element={<AdminCuentaDetalle />} />
            </Route>
            {/* Ruta de nivel superior propia, no anidada bajo cuentas: se
                navega aquí desde la ficha de una cuenta (Fase 14) y se
                vuelve a ella al cerrar. */}
            <Route path="/admin/organizaciones/:id" element={<AdminOrganizacionDetalle />} />
            <Route path="/admin/tarifas" element={<AdminTarifas />}>
              <Route path="nueva" element={<TarifaCrear />} />
              <Route path=":id" element={<AdminTarifaDetalle />} />
            </Route>
            <Route path="/admin/personal-plataforma" element={<AdminPersonalPlataforma />}>
              <Route path="nuevo" element={<PersonalPlataformaCrear />} />
              <Route path=":id" element={<AdminPersonalPlataformaDetalle />} />
            </Route>
            <Route path="/admin/ajustes" element={<AdminAjustesGlobales />} />
          </>
        )}

        <Route
          path="*"
          element={<Placeholder title="No encontrado" phase="ruta no registrada" />}
        />
      </Routes>
    </AppShell>
  )
}

/** Pantalla a página completa para los estados en los que todavía no hay
 *  aplicación que mostrar: arranque, sin sesión y error de conexión. */
function Portada({ children }: { children: ReactNode }) {
  return (
    <div className="portada-sesion">
      <div className="portada-sesion__caja">
        <img src={logo} alt="Flexómetro" style={{ height: 40, width: 'auto', marginBottom: 'var(--sp-4)' }} />
        <p className="muted" style={{ marginBottom: 'var(--sp-5)' }}>
          ERP de construcción
        </p>
        {children}
      </div>
    </div>
  )
}

export function App() {
  return (
    <ToastProvider>
      <WorkspaceProvider>
        <Workspace />
      </WorkspaceProvider>
    </ToastProvider>
  )
}
