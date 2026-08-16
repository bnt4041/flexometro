import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { ErrorNotice, Field, ModalPantalla, PruebaSmtpCard } from '../components/ui'
import { api } from '../lib/api'
import type { OrganizacionAdminDetalle as Detalle } from '../lib/api'
import { useToast } from '../toast'
import { UsuariosYGruposCard } from './UsuariosYGruposCard'

/** Ficha de una organización — desde la Fase 14 es una ruta de nivel
 *  superior propia (no cuelga de un listado con Outlet): toda organización
 *  nace dentro de una cuenta y se navega hasta aquí desde la ficha de esa
 *  cuenta (`AdminCuentaDetalle.tsx`), a la que se vuelve al cerrar. La
 *  facturación SaaS (tarifa, coste estimado, cobros, descuentos, uso de IA)
 *  vive en la cuenta, no aquí — esta ficha solo tiene lo que sigue siendo
 *  por organización: módulos activos, correo saliente propio, usuarios y
 *  grupos. */
export function AdminOrganizacionDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const [organizacion, setOrganizacion] = useState<Detalle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyModulo, setBusyModulo] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setOrganizacion(await api.admin.organizaciones.get(id))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate(organizacion ? `/admin/cuentas/${organizacion.cuenta_id}` : '/admin/cuentas')
  }

  if (error && !organizacion) {
    return (
      <ModalPantalla title="Organización" onClose={() => navigate('/admin/cuentas')}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!organizacion) return null

  async function toggleModulo(code: string, active: boolean) {
    setBusyModulo(code)
    try {
      await api.admin.organizaciones.setModuleActive(id, code, active)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusyModulo(null)
    }
  }

  return (
    <ModalPantalla
      title={
        <>
          {organizacion.name} <span className="table__code">{organizacion.slug}</span>
        </>
      }
      onClose={cerrar}
    >
      <ErrorNotice error={error} />

      <DatosOrganizacion organizacion={organizacion} onCambio={cargar} />

      <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, margin: 'var(--sp-6) 0 var(--sp-3)' }}>
        Módulos
      </h2>
      <p className="page-lead">
        Activar uno arrastra sus dependencias; no se puede desactivar un módulo del que
        dependan otros activos en esta misma organización.
      </p>

      <div className="card">
        {organizacion.modulos.map((modulo) => (
          <div className="module-row" key={modulo.code}>
            <div>
              <div className="module-row__title">
                {modulo.name}
                {modulo.always_active && <span className="badge badge--core">núcleo</span>}
              </div>
              {modulo.depends_on.length > 0 && (
                <div className="module-row__deps">requiere: {modulo.depends_on.join(', ')}</div>
              )}
            </div>
            <button
              className={modulo.is_active ? 'btn' : 'btn btn--primary'}
              disabled={modulo.always_active || busyModulo !== null}
              onClick={() => void toggleModulo(modulo.code, !modulo.is_active)}
            >
              {busyModulo === modulo.code
                ? '...'
                : modulo.always_active
                  ? 'Siempre activo'
                  : modulo.is_active
                    ? 'Desactivar'
                    : 'Activar'}
            </button>
          </div>
        ))}
      </div>

      <SmtpOrganizacionCard organizationId={id} />
      <UsuariosYGruposCard api={api.admin.organizaciones.usuariosYGrupos(id)} />
    </ModalPantalla>
  )
}

function DatosOrganizacion({
  organizacion,
  onCambio,
}: {
  organizacion: Detalle
  onCambio: () => Promise<void>
}) {
  const [name, setName] = useState(organizacion.name)
  const [cif, setCif] = useState(organizacion.cif ?? '')
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.organizaciones.update(organizacion.id, { name, cif: cif || null })
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
      await api.admin.organizaciones.update(organizacion.id, {
        is_active: !organizacion.is_active,
      })
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
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="CIF">
          <input className="input" value={cif} onChange={(e) => setCif(e.target.value)} />
        </Field>
      </div>
      <div className="form-actions" style={{ justifyContent: 'space-between' }}>
        <button
          className={organizacion.is_active ? 'btn btn--danger' : 'btn'}
          disabled={guardando}
          onClick={() => void toggleActiva()}
        >
          {organizacion.is_active ? 'Desactivar organización' : 'Reactivar organización'}
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

function SmtpOrganizacionCard({ organizationId }: { organizationId: string }) {
  const { notificar } = useToast()
  const [host, setHost] = useState('')
  const [puerto, setPuerto] = useState('587')
  const [usuario, setUsuario] = useState('')
  const [password, setPassword] = useState('')
  const [remitente, setRemitente] = useState('')
  const [tienePassword, setTienePassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const config = await api.admin.organizaciones.smtp.get(organizationId)
      setHost(config.host ?? '')
      setPuerto(String(config.puerto))
      setUsuario(config.usuario ?? '')
      setRemitente(config.remitente ?? '')
      setTienePassword(config.tiene_password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [organizationId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.organizaciones.smtp.update(organizationId, {
        host,
        puerto: Number(puerto),
        usuario,
        password: password || undefined,
        remitente,
      })
      setPassword('')
      await cargar()
      notificar('SMTP de la organización guardado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Seccion
      titulo="Correo saliente propio"
      nota="SMTP con el que esta organización envía SU correo (por ejemplo, sus facturas a sus clientes) — distinto del SMTP de la plataforma."
    >
      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field label="Host">
            <input className="input" value={host} onChange={(e) => setHost(e.target.value)} />
          </Field>
          <Field label="Puerto">
            <input className="input" value={puerto} onChange={(e) => setPuerto(e.target.value)} />
          </Field>
          <Field label="Usuario">
            <input className="input" value={usuario} onChange={(e) => setUsuario(e.target.value)} />
          </Field>
          <Field label="Contraseña" hint={tienePassword ? 'Configurada' : 'Sin configurar'}>
            <input
              className="input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={tienePassword ? '••••••••' : ''}
            />
          </Field>
          <Field label="Remitente">
            <input className="input" value={remitente} onChange={(e) => setRemitente(e.target.value)} />
          </Field>
        </div>
        <div className="form-actions">
          <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
            {guardando ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
        <PruebaSmtpCard
          onProbar={(destinatario) => api.admin.organizaciones.smtp.probar(organizationId, destinatario)}
        />
      </div>
    </Seccion>
  )
}
