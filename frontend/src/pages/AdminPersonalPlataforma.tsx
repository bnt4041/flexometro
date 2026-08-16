import { useCallback, useEffect, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'

import { EmptyState, ErrorNotice, Field, ModalPantalla } from '../components/ui'
import { api } from '../lib/api'
import type { UsuarioKeycloak } from '../lib/api'

export type ContextoPersonalPlataforma = { onCambio: () => void }

export function useContextoPersonalPlataforma() {
  return useOutletContext<ContextoPersonalPlataforma>()
}

export function AdminPersonalPlataforma() {
  const [items, setItems] = useState<UsuarioKeycloak[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setItems(await api.admin.personalPlataforma.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function toggleHabilitado(usuario: UsuarioKeycloak) {
    setBusy(usuario.id)
    setError(null)
    try {
      await api.admin.personalPlataforma.update(usuario.id, { habilitado: !usuario.enabled })
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusy(null)
    }
  }

  async function reenviar(usuario: UsuarioKeycloak) {
    setBusy(usuario.id)
    setError(null)
    try {
      await api.admin.personalPlataforma.reenviar(usuario.id, {
        username: usuario.username,
        email: usuario.email ?? '',
        nombre: usuario.firstName ?? usuario.username,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusy(null)
    }
  }

  async function eliminar(usuario: UsuarioKeycloak) {
    if (!window.confirm(`¿Eliminar a «${usuario.username}» del personal de la plataforma?`)) return
    setBusy(usuario.id)
    setError(null)
    try {
      await api.admin.personalPlataforma.remove(usuario.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Personal de la plataforma</h1>
          <p className="page-lead">
            Quien tiene acceso a Administración sobre cualquier organización. No pertenecen a
            ninguna organización — a diferencia de los usuarios de un tenant, que siempre son de
            una en concreto.
          </p>
        </div>
        <Link className="btn btn--primary" to="nuevo">
          Nueva persona
        </Link>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="No hay personal de la plataforma todavía" />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Correo</th>
                <th>Nombre</th>
                <th>Estado</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {items.map((u) => (
                <tr key={u.id}>
                  <td className="table__code">{u.username}</td>
                  <td>{u.email ?? '—'}</td>
                  <td>{[u.firstName, u.lastName].filter(Boolean).join(' ') || '—'}</td>
                  <td>
                    <span className={`chip ${u.enabled ? 'chip--proveedor' : 'chip--inactivo'}`}>
                      {u.enabled ? 'activo' : 'deshabilitado'}
                    </span>
                  </td>
                  <td className="table__actions">
                    <Link className="btn btn--sm" to={`${u.id}`}>
                      Editar
                    </Link>
                    <button
                      className="btn btn--sm"
                      disabled={busy === u.id}
                      onClick={() => void toggleHabilitado(u)}
                    >
                      {u.enabled ? 'Deshabilitar' : 'Habilitar'}
                    </button>
                    <button className="btn btn--sm" disabled={busy === u.id} onClick={() => void reenviar(u)}>
                      Reenviar invitación
                    </button>
                    <button
                      className="btn btn--sm btn--danger"
                      disabled={busy === u.id}
                      onClick={() => void eliminar(u)}
                    >
                      Eliminar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoPersonalPlataforma} />
    </>
  )
}

export function PersonalPlataformaCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoPersonalPlataforma()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [nombre, setNombre] = useState('')
  const [apellidos, setApellidos] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  function cerrar() {
    navigate('/admin/personal-plataforma')
  }

  async function crear() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.personalPlataforma.create({ username, email, nombre, apellidos })
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Nueva persona de la plataforma" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <p className="form-section__note">
            Nace con el rol <code>superadmin</code> y sin organización — entra directamente a
            Administración, no a ningún tenant.
          </p>
          <div className="form-grid">
            <Field label="Usuario">
              <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
            </Field>
            <Field label="Correo">
              <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Nombre">
              <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
            </Field>
            <Field label="Apellidos">
              <input className="input" value={apellidos} onChange={(e) => setApellidos(e.target.value)} />
            </Field>
          </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || !username || !email || !nombre || !apellidos}
            onClick={() => void crear()}
          >
            {guardando ? 'Creando…' : 'Crear'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
