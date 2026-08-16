import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { ErrorNotice, Field, ModalPantalla } from '../components/ui'
import { api } from '../lib/api'
import type { UsuarioKeycloak } from '../lib/api'
import { useContextoPersonalPlataforma } from './AdminPersonalPlataforma'

export function AdminPersonalPlataformaDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoPersonalPlataforma()
  const [usuario, setUsuario] = useState<UsuarioKeycloak | null>(null)
  const [email, setEmail] = useState('')
  const [nombre, setNombre] = useState('')
  const [apellidos, setApellidos] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const lista = await api.admin.personalPlataforma.list()
      const encontrado = lista.find((u) => u.id === id) ?? null
      setUsuario(encontrado)
      if (encontrado) {
        setEmail(encontrado.email ?? '')
        setNombre(encontrado.firstName ?? '')
        setApellidos(encontrado.lastName ?? '')
      }
      setError(encontrado ? null : 'No se ha encontrado esta persona')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/admin/personal-plataforma')
  }

  if (error && !usuario) {
    return (
      <ModalPantalla title="Personal de la plataforma" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!usuario) return null

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.personalPlataforma.update(id, { email, nombre, apellidos })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title={`Editar «${usuario.username}»`} onClose={cerrar}>
      <ErrorNotice error={error} />
      <div className="card">
        <div className="form-grid">
          <Field label="Correo">
            <input className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          </Field>
          <Field label="Nombre">
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Field>
          <Field label="Apellidos">
            <input className="input" value={apellidos} onChange={(e) => setApellidos(e.target.value)} />
          </Field>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={cerrar}>
            Cerrar
          </button>
          <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
            {guardando ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}
