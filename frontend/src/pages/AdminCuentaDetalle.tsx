import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Checkbox, ErrorNotice, Field, Modal, ModalPantalla, formatoImporte } from '../components/ui'
import { NumeracionCard } from '../components/NumeracionCard'
import { api } from '../lib/api'
import type {
  CobroSaas,
  CosteEstimado,
  CuentaAdminDetalle as Detalle,
  OrganizacionAdmin,
  Tarifa,
  UsoIA,
} from '../lib/api'
import { AplicacionesDescuentoCard } from './AplicacionesDescuentoCard'
import { useContextoAdminCuentas } from './AdminCuentas'

export function AdminCuentaDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoAdminCuentas()
  const [cuenta, setCuenta] = useState<Detalle | null>(null)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setCuenta(await api.admin.cuentas.get(id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    // La lista de cuentas no se refresca en cada guardado de esta ficha
    // (nombre, tarifa...), solo al volver a verla — mismo motivo que ya
    // aplicaba a la ficha de organización antes de la Fase 14.
    onCambio()
    navigate('/admin/cuentas')
  }

  if (error && !cuenta) {
    return (
      <ModalPantalla title="Cuenta" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!cuenta) return null

  return (
    <ModalPantalla title={cuenta.nombre} onClose={cerrar}>
      <ErrorNotice error={error} />

      <DatosCuenta cuenta={cuenta} onCambio={cargar} />

      <OrganizacionesDeCuenta cuentaId={id} />

      <NumeracionCard
        cifsDistintos={cuenta.cifs_distintos}
        listar={() => api.admin.cuentas.patronesNumeracion.list(id)}
        actualizar={(tipo, datos) => api.admin.cuentas.patronesNumeracion.update(id, tipo, datos)}
      />

      <CosteEstimadoCard cuentaId={id} />

      <Seccion
        titulo="Descuentos"
        nota="Histórico de descuentos aplicados a esta cuenta. Se crean en Tarifas; aquí solo se buscan, se aplican y se anulan."
      >
        <AplicacionesDescuentoCard cuentaId={id} />
      </Seccion>

      <CobrosCard cuentaId={id} />
      <UsoIACard cuentaId={id} />
    </ModalPantalla>
  )
}

function DatosCuenta({ cuenta, onCambio }: { cuenta: Detalle; onCambio: () => Promise<void> }) {
  const [nombre, setNombre] = useState(cuenta.nombre)
  const [tarifas, setTarifas] = useState<Tarifa[]>([])
  const [tarifaId, setTarifaId] = useState(cuenta.tarifa_id ?? '')
  const [compartirMaestros, setCompartirMaestros] = useState(cuenta.compartir_maestros)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api.admin.tarifas.list().then(setTarifas)
  }, [])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.cuentas.update(cuenta.id, {
        nombre,
        tarifa_id: tarifaId || null,
        compartir_maestros: compartirMaestros,
      })
      await onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function toggleActiva() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.cuentas.update(cuenta.id, { is_active: !cuenta.is_active })
      await onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="card" style={{ padding: 'var(--sp-5)' }}>
      <ErrorNotice error={error} />
      <div className="form-grid">
        <Field label="Nombre">
          <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </Field>
        <Field label="Tarifa" hint="Cubre todas las organizaciones de esta cuenta">
          <select className="select" value={tarifaId} onChange={(e) => setTarifaId(e.target.value)}>
            <option value="">Sin tarifa asignada</option>
            {tarifas.map((t) => (
              <option key={t.id} value={t.id}>
                {t.nombre}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <div style={{ marginTop: 'var(--sp-4)' }}>
        <Checkbox
          label="Compartir maestros entre las organizaciones de esta cuenta"
          checked={compartirMaestros}
          onChange={setCompartirMaestros}
        />
        <p className="page-lead" style={{ marginTop: 'var(--sp-1)' }}>
          Terceros, catálogo y cuadro de precios se ven (solo lectura) entre las organizaciones
          de esta cuenta. Presupuestos, obras, facturas y albaranes nunca se comparten — están
          atados por ley a un CIF concreto.
        </p>
      </div>
      <div className="form-actions" style={{ justifyContent: 'space-between' }}>
        <button
          className={cuenta.is_active ? 'btn btn--danger' : 'btn'}
          disabled={guardando}
          onClick={() => void toggleActiva()}
        >
          {cuenta.is_active ? 'Desactivar cuenta' : 'Reactivar cuenta'}
        </button>
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {guardando ? 'Guardando…' : 'Guardar datos'}
        </button>
      </div>
    </div>
  )
}

function Seccion({ titulo, nota, children }: { titulo: string; nota?: string; children: ReactNode }) {
  return (
    <>
      <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, margin: 'var(--sp-6) 0 var(--sp-3)' }}>
        {titulo}
      </h2>
      {nota && <p className="page-lead">{nota}</p>}
      {children}
    </>
  )
}

function OrganizacionesDeCuenta({ cuentaId }: { cuentaId: string }) {
  const navigate = useNavigate()
  const [items, setItems] = useState<OrganizacionAdmin[]>([])
  const [error, setError] = useState<string | null>(null)
  const [creando, setCreando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setItems(await api.admin.cuentas.organizaciones.list(cuentaId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [cuentaId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <Seccion
      titulo="Organizaciones"
      nota="Cada una es una empresa/CIF con sus propios módulos, usuarios y datos de negocio, aislados del resto — la cuenta solo agrupa su contrato."
    >
      <div className="page-head" style={{ marginBottom: 'var(--sp-3)' }}>
        <div />
        <button className="btn" onClick={() => setCreando(true)}>
          Nueva organización
        </button>
      </div>

      <ErrorNotice error={error} />

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Slug</th>
              <th>Nombre</th>
              <th>CIF</th>
              <th>Estado</th>
              <th className="table__actions" />
            </tr>
          </thead>
          <tbody>
            {items.map((org) => (
              <tr key={org.id}>
                <td className="table__code">{org.slug}</td>
                <td>{org.name}</td>
                <td>{org.cif ?? <span className="muted">—</span>}</td>
                <td>
                  <span className={`chip ${org.is_active ? 'chip--proveedor' : 'chip--inactivo'}`}>
                    {org.is_active ? 'activa' : 'desactivada'}
                  </span>
                </td>
                <td className="table__actions">
                  <Link className="btn btn--sm" to={`/admin/organizaciones/${org.id}`}>
                    Gestionar
                  </Link>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  Sin organizaciones todavía
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {creando && (
        <NuevaOrganizacionModal
          cuentaId={cuentaId}
          onClose={() => setCreando(false)}
          onCreada={async (org) => {
            setCreando(false)
            await cargar()
            navigate(`/admin/organizaciones/${org.id}`)
          }}
        />
      )}
    </Seccion>
  )
}

function NuevaOrganizacionModal({
  cuentaId,
  onClose,
  onCreada,
}: {
  cuentaId: string
  onClose: () => void
  onCreada: (organizacion: OrganizacionAdmin) => Promise<void>
}) {
  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [cif, setCif] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const organizacion = await api.admin.cuentas.organizaciones.create(cuentaId, {
        slug,
        name,
        cif: cif || undefined,
      })
      await onCreada(organizacion)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title="Nueva organización" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          La organización nace sin ningún módulo activo salvo el núcleo; se activan uno a uno
          desde su ficha.
        </p>
        <div className="form-grid">
          <Field label="Slug" hint="minúsculas, dígitos y guiones — es el que usa Keycloak">
            <input className="input" value={slug} onChange={(e) => setSlug(e.target.value)} autoFocus />
          </Field>
          <Field label="Nombre">
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="CIF" hint="Opcional">
            <input className="input" value={cif} onChange={(e) => setCif(e.target.value)} />
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={guardando || slug.trim() === '' || name.trim() === ''}
          onClick={() => void guardar()}
        >
          {guardando ? 'Creando…' : 'Crear organización'}
        </button>
      </div>
    </Modal>
  )
}

function CosteEstimadoCard({ cuentaId }: { cuentaId: string }) {
  const [coste, setCoste] = useState<CosteEstimado | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.admin.cuentas
      .costeEstimado(cuentaId)
      .then(setCoste)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [cuentaId])

  return (
    <Seccion
      titulo="Coste estimado este mes"
      nota="Suma de todas las organizaciones de la cuenta: módulos activos + tokens de IA consumidos, con los descuentos vigentes ya aplicados."
    >
      <ErrorNotice error={error} />
      {coste && (
        <div className="card resumen-totales" style={{ padding: 'var(--sp-5)' }}>
          {!coste.tarifa_nombre && (
            <div className="notice notice--aviso" style={{ marginBottom: 'var(--sp-3)' }}>
              Sin tarifa asignada: el coste no se puede calcular todavía.
            </div>
          )}
          <div className="resumen-totales__fila">
            <span>Módulos activos</span>
            <span className="resumen-totales__valor">{formatoImporte(coste.subtotal_modulos)} €</span>
          </div>
          <div className="resumen-totales__fila is-suave">
            <span>
              IA ({coste.tokens_deepseek_mes.toLocaleString('es-ES')} tok. DeepSeek +{' '}
              {coste.tokens_gemini_mes.toLocaleString('es-ES')} tok. Gemini)
            </span>
            <span className="resumen-totales__valor">{formatoImporte(coste.subtotal_ia)} €</span>
          </div>
          {Number(coste.descuentos_aplicados) > 0 && (
            <div className="resumen-totales__fila is-suave">
              <span>Descuentos aplicados</span>
              <span className="resumen-totales__valor">-{formatoImporte(coste.descuentos_aplicados)} €</span>
            </div>
          )}
          <div className="resumen-totales__fila is-total">
            <span>Total estimado</span>
            <span className="resumen-totales__valor">{formatoImporte(coste.total)} €</span>
          </div>
        </div>
      )}
    </Seccion>
  )
}

function CobrosCard({ cuentaId }: { cuentaId: string }) {
  const [cobros, setCobros] = useState<CobroSaas[]>([])
  const [concepto, setConcepto] = useState('')
  const [importe, setImporte] = useState('')
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setCobros(await api.admin.cuentas.cobros.list(cuentaId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [cuentaId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function registrar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.cuentas.cobros.create(cuentaId, { concepto, importe, fecha })
      setConcepto('')
      setImporte('')
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Seccion titulo="Cobros" nota="Registrados a mano por ahora; es el mismo hueco donde encajará el webhook de Paddle.">
      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field label="Concepto">
            <input className="input" value={concepto} onChange={(e) => setConcepto(e.target.value)} />
          </Field>
          <Field label="Importe">
            <input className="input" value={importe} onChange={(e) => setImporte(e.target.value)} />
          </Field>
          <Field label="Fecha">
            <input className="input" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </Field>
        </div>
        <div className="form-actions">
          <button
            className="btn btn--primary"
            disabled={guardando || !concepto || !importe}
            onClick={() => void registrar()}
          >
            {guardando ? 'Registrando…' : 'Registrar cobro'}
          </button>
        </div>
      </div>

      <div className="table-wrap" style={{ marginTop: 'var(--sp-3)' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Concepto</th>
              <th className="table__num">Importe</th>
              <th>Origen</th>
            </tr>
          </thead>
          <tbody>
            {cobros.map((c) => (
              <tr key={c.id}>
                <td>{c.fecha}</td>
                <td>{c.concepto}</td>
                <td className="table__num">{formatoImporte(c.importe)} €</td>
                <td className="muted">{c.origen}</td>
              </tr>
            ))}
            {cobros.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  Sin cobros registrados
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Seccion>
  )
}

function UsoIACard({ cuentaId }: { cuentaId: string }) {
  const [items, setItems] = useState<UsoIA[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.admin.cuentas
      .usoIA(cuentaId, { limit: 20 })
      .then(setItems)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [cuentaId])

  return (
    <Seccion
      titulo="Uso de IA por usuario"
      nota="Últimos 20 eventos de todas las organizaciones de la cuenta: quién ha consumido tokens y de qué proveedor."
    >
      <ErrorNotice error={error} />
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Usuario</th>
              <th>Proveedor</th>
              <th>Modelo</th>
              <th className="table__num">Tok. entrada</th>
              <th className="table__num">Tok. salida</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id}>
                <td className="muted">{u.created_at.slice(0, 16).replace('T', ' ')}</td>
                <td>{u.usuario_nombre}</td>
                <td>{u.proveedor}</td>
                <td className="muted">{u.modelo}</td>
                <td className="table__num">{u.tokens_entrada}</td>
                <td className="table__num">{u.tokens_salida}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  Sin uso de IA registrado todavía
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Seccion>
  )
}
