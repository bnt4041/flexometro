import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal, Tooltip } from './ui'
import { api } from '../lib/api'
import type { Contacto, ContactoAsociado, EntidadContacto } from '../lib/api'
import { useToast } from '../toast'

/** Pestaña "Contactos asociados" (Fase 28) de cualquier objeto grande del
 *  negocio (presupuesto, obra, certificación, factura) — no confundir con
 *  los contactos de un Tercero: aquí se asocia un `Contacto` ya existente
 *  (de cualquier tercero, o suelto) a este registro concreto, con un rol
 *  libre ("decisor", "técnico de obra"...). */
export function ContactosAsociados({ entidad, entidadId }: { entidad: EntidadContacto; entidadId: string }) {
  const { notificar } = useToast()
  const [asociados, setAsociados] = useState<ContactoAsociado[]>([])
  const [error, setError] = useState<string | null>(null)
  const [nuevo, setNuevo] = useState(false)

  const cargar = useCallback(async () => {
    try {
      setAsociados(await api.contactosAsociados.list(entidad, entidadId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entidad, entidadId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function eliminar(asociado: ContactoAsociado) {
    if (!window.confirm(`¿Quitar a «${asociado.contacto_nombre}» de este registro?`)) return
    try {
      await api.contactosAsociados.remove(asociado.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          Personas involucradas en este registro.
        </p>
        <Tooltip texto="Asociar un contacto existente">
          <button className="btn" onClick={() => setNuevo(true)}>
            <Plus size={16} aria-hidden="true" />
            Asociar contacto
          </button>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      <div className="table-wrap">
        {asociados.length === 0 ? (
          <EmptyState title="Sin contactos asociados">
            Asocia a las personas involucradas en este registro.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Cargo</th>
                <th>Rol</th>
                <th>Email</th>
                <th>Teléfono</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {asociados.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.contacto_nombre} {a.contacto_apellidos ?? ''}
                  </td>
                  <td>{a.contacto_cargo ?? <span className="muted">—</span>}</td>
                  <td>{a.rol ?? <span className="muted">—</span>}</td>
                  <td>{a.contacto_email ?? <span className="muted">—</span>}</td>
                  <td>{a.contacto_telefono ?? <span className="muted">—</span>}</td>
                  <td className="table__actions">
                    <button className="btn btn--sm btn--danger" onClick={() => void eliminar(a)}>
                      <Trash2 size={14} aria-hidden="true" />
                      Quitar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {nuevo && (
        <AsociarContactoModal
          entidad={entidad}
          entidadId={entidadId}
          excluir={asociados.map((a) => a.contacto_id)}
          onClose={() => setNuevo(false)}
          onCreado={() => {
            setNuevo(false)
            void cargar()
            notificar('Contacto asociado')
          }}
        />
      )}
    </>
  )
}

function AsociarContactoModal({
  entidad,
  entidadId,
  excluir,
  onClose,
  onCreado,
}: {
  entidad: EntidadContacto
  entidadId: string
  excluir: string[]
  onClose: () => void
  onCreado: () => void
}) {
  const [q, setQ] = useState('')
  const [resultados, setResultados] = useState<Contacto[]>([])
  const [seleccionado, setSeleccionado] = useState<Contacto | null>(null)
  const [rol, setRol] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  // Si la persona no existe todavía como Contacto, se crea aquí mismo — sin
  // salir a Terceros/Contactos y perder lo que ya se llevaba en esta ficha.
  const [creandoNuevo, setCreandoNuevo] = useState(false)
  const [nombreNuevo, setNombreNuevo] = useState('')
  const [apellidosNuevo, setApellidosNuevo] = useState('')
  const [cargoNuevo, setCargoNuevo] = useState('')
  const [emailNuevo, setEmailNuevo] = useState('')
  const [telefonoNuevo, setTelefonoNuevo] = useState('')

  useEffect(() => {
    let cancelado = false
    async function buscar() {
      try {
        const pagina = await api.contactos.list({ q: q || undefined, limit: 20 })
        if (!cancelado) setResultados(pagina.items.filter((c) => !excluir.includes(c.id)))
      } catch {
        setResultados([])
      }
    }
    void buscar()
    return () => {
      cancelado = true
    }
  }, [q, excluir])

  async function guardar() {
    if (!seleccionado) return
    setGuardando(true)
    setError(null)
    try {
      await api.contactosAsociados.create(entidad, entidadId, {
        contacto_id: seleccionado.id,
        rol: rol || null,
      })
      onCreado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  async function guardarNuevo() {
    setGuardando(true)
    setError(null)
    try {
      const contacto = await api.contactos.create({
        nombre: nombreNuevo,
        apellidos: apellidosNuevo || null,
        cargo: cargoNuevo || null,
        email: emailNuevo || null,
        telefono: telefonoNuevo || null,
      })
      await api.contactosAsociados.create(entidad, entidadId, {
        contacto_id: contacto.id,
        rol: rol || null,
      })
      onCreado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title={creandoNuevo ? 'Nuevo contacto' : 'Asociar contacto'} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        {creandoNuevo ? (
          <>
            <button
              type="button"
              className="btn btn--sm"
              style={{ marginBottom: 'var(--sp-3)' }}
              onClick={() => setCreandoNuevo(false)}
            >
              ← Volver a buscar
            </button>
            <div className="form-grid">
              <Field label="Nombre">
                <input
                  className="input"
                  value={nombreNuevo}
                  onChange={(e) => setNombreNuevo(e.target.value)}
                  autoFocus
                />
              </Field>
              <Field label="Apellidos">
                <input
                  className="input"
                  value={apellidosNuevo}
                  onChange={(e) => setApellidosNuevo(e.target.value)}
                />
              </Field>
              <Field label="Cargo">
                <input
                  className="input"
                  value={cargoNuevo}
                  onChange={(e) => setCargoNuevo(e.target.value)}
                />
              </Field>
              <Field ancho="doble" label="Email">
                <input
                  className="input"
                  value={emailNuevo}
                  onChange={(e) => setEmailNuevo(e.target.value)}
                />
              </Field>
              <Field label="Teléfono">
                <input
                  className="input"
                  value={telefonoNuevo}
                  onChange={(e) => setTelefonoNuevo(e.target.value)}
                />
              </Field>
              <Field ancho="doble" label="Rol en este registro">
                <input
                  className="input"
                  value={rol}
                  onChange={(e) => setRol(e.target.value)}
                  placeholder="p. ej. decisor, técnico de obra…"
                />
              </Field>
            </div>
          </>
        ) : (
          <>
            <Field label="Buscar por nombre, apellidos o email">
              <input
                className="input"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value)
                  setSeleccionado(null)
                }}
                autoFocus
                placeholder="Escribe para buscar…"
              />
            </Field>
            {!seleccionado && (
              <div className="table-wrap" style={{ maxHeight: 220, overflowY: 'auto' }}>
                {resultados.length === 0 ? (
                  <p className="muted" style={{ padding: 'var(--sp-3)' }}>
                    Sin resultados.
                  </p>
                ) : (
                  <table className="table">
                    <tbody>
                      {resultados.map((c) => (
                        <tr key={c.id} onClick={() => setSeleccionado(c)} style={{ cursor: 'pointer' }}>
                          <td>
                            {c.nombre} {c.apellidos ?? ''}
                          </td>
                          <td>{c.cargo ?? <span className="muted">—</span>}</td>
                          <td>{c.email ?? <span className="muted">—</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
            {!seleccionado && (
              <button
                type="button"
                className="btn btn--sm"
                style={{ marginTop: 'var(--sp-2)' }}
                onClick={() => setCreandoNuevo(true)}
              >
                <Plus size={14} aria-hidden="true" />
                ¿No existe? Crear contacto nuevo
              </button>
            )}
            {seleccionado && (
              <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
                <Field ancho="doble" label="Contacto seleccionado">
                  <div className="chip chip--cliente">
                    {seleccionado.nombre} {seleccionado.apellidos ?? ''}
                  </div>
                </Field>
                <Field label="Rol en este registro">
                  <input
                    className="input"
                    value={rol}
                    onChange={(e) => setRol(e.target.value)}
                    placeholder="p. ej. decisor, técnico de obra…"
                  />
                </Field>
              </div>
            )}
          </>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        {creandoNuevo ? (
          <button
            className="btn btn--primary"
            disabled={nombreNuevo.trim() === '' || guardando}
            onClick={() => void guardarNuevo()}
          >
            <Plus size={16} aria-hidden="true" />
            {guardando ? 'Creando…' : 'Crear y asociar'}
          </button>
        ) : (
          <button
            className="btn btn--primary"
            disabled={!seleccionado || guardando}
            onClick={() => void guardar()}
          >
            <Plus size={16} aria-hidden="true" />
            {guardando ? 'Asociando…' : 'Asociar'}
          </button>
        )}
      </div>
    </Modal>
  )
}
