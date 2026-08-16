import { useCallback, useEffect, useState } from 'react'
import { Link, Outlet, useNavigate, useOutletContext } from 'react-router-dom'
import { ArrowRight, Plus, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, ModalPantalla } from '../components/ui'
import { api } from '../lib/api'
import type { CuentaAdmin } from '../lib/api'

export type ContextoAdminCuentas = { onCambio: () => void }

export function useContextoAdminCuentas() {
  return useOutletContext<ContextoAdminCuentas>()
}

export function AdminCuentas() {
  const [items, setItems] = useState<CuentaAdmin[]>([])
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      setItems(await api.admin.cuentas.list())
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

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Cuentas</h1>
          <p className="page-lead">
            El contrato de cada cliente: puede agrupar varias organizaciones (empresas/CIFs)
            bajo un mismo contrato consolidado. Esta pantalla solo la ven las cuentas con el
            rol <code>superadmin</code>.
          </p>
        </div>
        <Link className="btn btn--primary" to="nueva">
          <Plus size={16} aria-hidden="true" />
          Nueva cuenta
        </Link>
      </div>

      <ErrorNotice error={error} />

      {!cargando && items.length === 0 ? (
        <EmptyState title="No hay cuentas todavía" />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Estado</th>
                <th>Creada</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {items.map((cuenta) => (
                <tr key={cuenta.id}>
                  <td>
                    <Link className="table__link" to={`${cuenta.id}`} style={{ fontWeight: 600 }}>
                      {cuenta.nombre}
                    </Link>
                  </td>
                  <td>
                    <span className={`chip ${cuenta.is_active ? 'chip--proveedor' : 'chip--inactivo'}`}>
                      {cuenta.is_active ? 'activa' : 'desactivada'}
                    </span>
                  </td>
                  <td className="muted">{cuenta.created_at.slice(0, 10)}</td>
                  <td className="table__actions">
                    <Link className="btn btn--sm" to={`${cuenta.id}`}>
                      Gestionar
                      <ArrowRight size={14} aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Outlet context={{ onCambio: cargar } satisfies ContextoAdminCuentas} />
    </>
  )
}

export function AdminCuentaCrear() {
  const navigate = useNavigate()
  const { onCambio } = useContextoAdminCuentas()
  const [nombre, setNombre] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  function cerrar() {
    navigate('/admin/cuentas')
  }

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const cuenta = await api.admin.cuentas.create({ nombre })
      onCambio()
      navigate(`/admin/cuentas/${cuenta.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Nueva cuenta" onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-section">
          <p className="form-section__note">
            La cuenta nace sin organizaciones ni tarifa asignada; se añaden desde su propia
            ficha.
          </p>
          <div className="form-grid">
            <Field label="Nombre">
              <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus />
            </Field>
          </div>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || nombre.trim() === ''}
            onClick={() => void guardar()}
          >
            {!guardando && <Plus size={16} aria-hidden="true" />}
            {guardando ? 'Creando…' : 'Crear cuenta'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
