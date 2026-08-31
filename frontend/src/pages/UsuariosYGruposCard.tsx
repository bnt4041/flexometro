import { useCallback, useEffect, useState } from 'react'
import { Mail, Pencil, Plus, Power, Save, Trash2, UserMinus, UserPlus, X } from 'lucide-react'

import { AvisosDeDestinatario } from '../components/AvisosDeDestinatario'
import { Checkbox, ErrorNotice, Field, ModalPantalla } from '../components/ui'
import type { Alcance, Grupo, ModuloDisponible, UsuarioKeycloak, UsuariosGruposAPI } from '../lib/api'
import { useToast } from '../toast'

/** Las cuatro acciones, en el mismo orden que `ACCIONES` del backend. */
const ACCIONES: [keyof PermisosModulo, string][] = [
  ['ver', 'Ver'],
  ['editar', 'Modificar'],
  ['crear', 'Crear'],
  ['borrar', 'Borrar'],
]

type PermisosModulo = { ver: Alcance; editar: Alcance; crear: Alcance; borrar: Alcance }

const PERMISO_VACIO: PermisosModulo = {
  ver: 'ninguno',
  editar: 'ninguno',
  crear: 'ninguno',
  borrar: 'ninguno',
}

const ETIQUETA_ALCANCE: Record<Alcance, string> = {
  ninguno: 'Ninguno',
  propios: 'Solo propios',
  todos: 'Todos',
}

/** Pantalla de "Usuarios y Grupos": mismo componente para el panel de
 *  superadmin (cualquier organización) y el autoservicio del tenant — lo
 *  único que cambia es a qué URLs apunta el objeto `api` que se le pasa,
 *  ver `admin.organizaciones.usuariosYGrupos(id)` vs. `api.usuariosYGrupos`.
 *
 *  Mismo patrón que el resto de la aplicación: los listados solo listan, el
 *  alta y el detalle (editar un usuario, gestionar un grupo) se abren en el
 *  modal gigante. Aquí vive con estado local en vez de ruta propia — este
 *  componente ya cuelga de un modal gigante con ruta cuando lo monta el
 *  panel de superadmin (la ficha de organización), y apilar una segunda
 *  ruta anidada ahí habría complicado el enrutado sin aportar nada que el
 *  estado local no resuelva igual de bien. */
export function UsuariosYGruposCard({ api }: { api: UsuariosGruposAPI }) {
  const [usuarios, setUsuarios] = useState<UsuarioKeycloak[]>([])
  const [grupos, setGrupos] = useState<Grupo[]>([])
  const [modulos, setModulos] = useState<ModuloDisponible[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    try {
      const [u, g, m] = await Promise.all([
        api.usuarios.list(),
        api.grupos.list(),
        api.modulosDisponibles(),
      ])
      setUsuarios(u)
      setGrupos(g)
      setModulos(m)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [api])

  useEffect(() => {
    void cargar()
  }, [cargar])

  if (cargando) return <p className="muted">Cargando…</p>

  return (
    <>
      <ErrorNotice error={error} />
      <UsuariosSeccion api={api.usuarios} usuarios={usuarios} onCambio={cargar} />
      <GruposSeccion
        api={api.grupos}
        grupos={grupos}
        modulos={modulos}
        usuarios={usuarios}
        onCambio={cargar}
      />
    </>
  )
}

function Seccion({
  titulo,
  nota,
  accion,
  children,
}: {
  titulo: string
  nota?: string
  accion?: { etiqueta: string; onClick: () => void }
  children: React.ReactNode
}) {
  return (
    <>
      <div className="page-head" style={{ margin: 'var(--sp-6) 0 var(--sp-3)' }}>
        <div>
          <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, marginBottom: nota ? 'var(--sp-1)' : 0 }}>
            {titulo}
          </h2>
          {nota && (
            <p className="page-lead" style={{ marginBottom: 0 }}>
              {nota}
            </p>
          )}
        </div>
        {accion && (
          <button className="btn btn--primary" onClick={accion.onClick}>
            <Plus size={16} aria-hidden="true" />
            {accion.etiqueta}
          </button>
        )}
      </div>
      {children}
    </>
  )
}

// --- Usuarios ---

function UsuariosSeccion({
  api,
  usuarios,
  onCambio,
}: {
  api: UsuariosGruposAPI['usuarios']
  usuarios: UsuarioKeycloak[]
  onCambio: () => Promise<void>
}) {
  const [creando, setCreando] = useState(false)
  const [editando, setEditando] = useState<UsuarioKeycloak | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const { notificar } = useToast()

  async function toggleHabilitado(usuario: UsuarioKeycloak) {
    setBusy(usuario.id)
    setError(null)
    try {
      await api.update(usuario.id, { habilitado: !usuario.enabled })
      await onCambio()
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
      const resultado = await api.reenviar(usuario.id, {
        username: usuario.username,
        email: usuario.email ?? '',
        nombre: usuario.firstName ?? usuario.username,
      })
      // La petición siempre responde 200 aunque el correo no llegue (el
      // envío es best-effort) — sin comprobar `email_enviado` el usuario no
      // tiene ninguna forma de saber si de verdad se ha reenviado la
      // invitación o si se ha quedado callado por un fallo de SMTP.
      if (resultado.email_enviado) {
        notificar(`Invitación reenviada a ${usuario.email}`)
      } else {
        setError(
          `La contraseña se ha reiniciado, pero el correo a ${usuario.email} no se pudo enviar — revisa la configuración SMTP.`,
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusy(null)
    }
  }

  async function eliminar(usuario: UsuarioKeycloak) {
    if (!window.confirm(`¿Eliminar el usuario «${usuario.username}»? No se puede deshacer.`)) return
    setBusy(usuario.id)
    setError(null)
    try {
      await api.remove(usuario.id)
      await onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusy(null)
    }
  }

  return (
    <Seccion
      titulo="Usuarios"
      nota="Un usuario nuevo entra con el mínimo permiso hasta que se le añade a un grupo — salvo que se marque como administrador."
      accion={{ etiqueta: 'Crear usuario', onClick: () => setCreando(true) }}
    >
      <ErrorNotice error={error} />
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Correo</th>
              <th>Nombre</th>
              <th>Rol</th>
              <th>Estado</th>
              <th className="table__actions" />
            </tr>
          </thead>
          <tbody>
            {usuarios.map((u) => (
              <tr key={u.id}>
                <td className="table__code">{u.username}</td>
                <td>{u.email ?? '—'}</td>
                <td>{[u.firstName, u.lastName].filter(Boolean).join(' ') || '—'}</td>
                <td className="muted">{u.roles.join(', ') || '—'}</td>
                <td>
                  <span className={`chip ${u.enabled ? 'chip--proveedor' : 'chip--inactivo'}`}>
                    {u.enabled ? 'activo' : 'deshabilitado'}
                  </span>
                </td>
                <td className="table__actions">
                  <button className="btn btn--sm" disabled={busy === u.id} onClick={() => setEditando(u)}>
                    <Pencil size={14} aria-hidden="true" />
                    Editar
                  </button>
                  <button
                    className="btn btn--sm"
                    disabled={busy === u.id}
                    onClick={() => void toggleHabilitado(u)}
                  >
                    <Power size={14} aria-hidden="true" />
                    {u.enabled ? 'Deshabilitar' : 'Habilitar'}
                  </button>
                  <button className="btn btn--sm" disabled={busy === u.id} onClick={() => void reenviar(u)}>
                    <Mail size={14} aria-hidden="true" />
                    Reenviar invitación
                  </button>
                  <button
                    className="btn btn--sm btn--danger"
                    disabled={busy === u.id}
                    onClick={() => void eliminar(u)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
            {usuarios.length === 0 && (
              <tr>
                <td colSpan={6} className="muted">
                  Sin usuarios todavía
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {creando && (
        <UsuarioCrearModal
          api={api}
          onClose={() => setCreando(false)}
          onCreado={async () => {
            setCreando(false)
            await onCambio()
          }}
        />
      )}

      {editando && (
        <UsuarioEditarModal
          api={api}
          usuario={editando}
          onClose={() => setEditando(null)}
          onGuardado={async () => {
            setEditando(null)
            await onCambio()
          }}
        />
      )}
    </Seccion>
  )
}

function UsuarioCrearModal({
  api,
  onClose,
  onCreado,
}: {
  api: UsuariosGruposAPI['usuarios']
  onClose: () => void
  onCreado: () => Promise<void>
}) {
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [nombre, setNombre] = useState('')
  const [apellidos, setApellidos] = useState('')
  const [esAdmin, setEsAdmin] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function crear() {
    setGuardando(true)
    setError(null)
    try {
      await api.create({ username, email, nombre, apellidos, es_admin: esAdmin })
      await onCreado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Crear usuario" onClose={onClose}>
      <ErrorNotice error={error} />
      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <div className="form-grid">
          <Field label="Usuario">
            <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
          </Field>
          <Field ancho="doble" label="Correo">
            <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Nombre">
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Field>
          <Field label="Apellidos">
            <input className="input" value={apellidos} onChange={(e) => setApellidos(e.target.value)} />
          </Field>
        </div>
        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Checkbox
            label="Administrador de la organización (acceso total, sin depender de grupos)"
            checked={esAdmin}
            onChange={setEsAdmin}
          />
        </div>
        <div className="form-actions">
          <button className="btn" onClick={onClose}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button
            className="btn btn--primary"
            disabled={guardando || !username || !email || !nombre || !apellidos}
            onClick={() => void crear()}
          >
            {!guardando && <Plus size={16} aria-hidden="true" />}
            {guardando ? 'Creando…' : 'Crear usuario'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}

function UsuarioEditarModal({
  api,
  usuario,
  onClose,
  onGuardado,
}: {
  api: UsuariosGruposAPI['usuarios']
  usuario: UsuarioKeycloak
  onClose: () => void
  onGuardado: () => Promise<void>
}) {
  const [email, setEmail] = useState(usuario.email ?? '')
  const [nombre, setNombre] = useState(usuario.firstName ?? '')
  const [apellidos, setApellidos] = useState(usuario.lastName ?? '')
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.update(usuario.id, { email, nombre, apellidos })
      await onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title={`Editar «${usuario.username}»`} onClose={onClose}>
      <ErrorNotice error={error} />
      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <div className="form-grid">
          <Field ancho="doble" label="Correo">
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
          <button className="btn" onClick={onClose}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
            {!guardando && <Save size={16} aria-hidden="true" />}
            {guardando ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
        <div className="form-section__title">Notificaciones</div>
        <AvisosDeDestinatario usuarioSubject={usuario.id} />
      </div>
    </ModalPantalla>
  )
}

// --- Grupos ---

function GruposSeccion({
  api,
  grupos,
  modulos,
  usuarios,
  onCambio,
}: {
  api: UsuariosGruposAPI['grupos']
  grupos: Grupo[]
  modulos: ModuloDisponible[]
  usuarios: UsuarioKeycloak[]
  onCambio: () => Promise<void>
}) {
  const [creando, setCreando] = useState(false)
  const [gestionando, setGestionando] = useState<Grupo | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function eliminar(grupo: Grupo) {
    if (!window.confirm(`¿Eliminar el grupo «${grupo.nombre}»?`)) return
    setError(null)
    try {
      await api.remove(grupo.id)
      await onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  // Si el grupo que se está gestionando cambia (tras guardar permisos o
  // miembros), el modal tiene que ver la versión fresca, no la que tenía al
  // abrirse.
  const grupoGestionado = gestionando ? (grupos.find((g) => g.id === gestionando.id) ?? gestionando) : null

  return (
    <Seccion
      titulo="Grupos y permisos"
      nota="Cada grupo da, por módulo, qué puede ver, modificar, crear y borrar: nada, solo lo propio, o todo. Pertenecer a varios grupos nunca resta, solo puede ampliar."
      accion={{ etiqueta: 'Crear grupo', onClick: () => setCreando(true) }}
    >
      <ErrorNotice error={error} />
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Grupo</th>
              <th>Descripción</th>
              <th className="table__num">Miembros</th>
              <th className="table__actions" />
            </tr>
          </thead>
          <tbody>
            {grupos.map((grupo) => (
              <tr key={grupo.id}>
                <td className="table__link" style={{ fontWeight: 600 }}>
                  {grupo.nombre}
                </td>
                <td>{grupo.descripcion ?? <span className="muted">—</span>}</td>
                <td className="table__num">{grupo.miembros.length}</td>
                <td className="table__actions">
                  <button className="btn btn--sm" onClick={() => setGestionando(grupo)}>
                    <Pencil size={14} aria-hidden="true" />
                    Gestionar
                  </button>
                  <button className="btn btn--sm btn--danger" onClick={() => void eliminar(grupo)}>
                    <Trash2 size={14} aria-hidden="true" />
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
            {grupos.length === 0 && (
              <tr>
                <td colSpan={4} className="muted">
                  Sin grupos todavía
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {creando && (
        <GrupoCrearModal
          api={api}
          onClose={() => setCreando(false)}
          onCreado={async () => {
            setCreando(false)
            await onCambio()
          }}
        />
      )}

      {grupoGestionado && (
        <GrupoGestionarModal
          grupo={grupoGestionado}
          modulos={modulos}
          usuarios={usuarios}
          api={api}
          onClose={() => setGestionando(null)}
          onCambio={onCambio}
        />
      )}
    </Seccion>
  )
}

function GrupoCrearModal({
  api,
  onClose,
  onCreado,
}: {
  api: UsuariosGruposAPI['grupos']
  onClose: () => void
  onCreado: () => Promise<void>
}) {
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function crear() {
    setGuardando(true)
    setError(null)
    try {
      await api.create({ nombre, descripcion: descripcion || null })
      await onCreado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <ModalPantalla title="Crear grupo" onClose={onClose}>
      <ErrorNotice error={error} />
      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <div className="form-grid">
          <Field label="Nombre del grupo">
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus />
          </Field>
          <Field ancho="doble" label="Descripción">
            <input className="input" value={descripcion} onChange={(e) => setDescripcion(e.target.value)} />
          </Field>
        </div>
        <div className="form-actions">
          <button className="btn" onClick={onClose}>
            <X size={16} aria-hidden="true" />
            Cancelar
          </button>
          <button className="btn btn--primary" disabled={guardando || !nombre} onClick={() => void crear()}>
            {!guardando && <Plus size={16} aria-hidden="true" />}
            {guardando ? 'Creando…' : 'Crear grupo'}
          </button>
        </div>
      </div>
    </ModalPantalla>
  )
}

function GrupoGestionarModal({
  grupo,
  modulos,
  usuarios,
  api,
  onClose,
  onCambio,
}: {
  grupo: Grupo
  modulos: ModuloDisponible[]
  usuarios: UsuarioKeycloak[]
  api: UsuariosGruposAPI['grupos']
  onClose: () => void
  onCambio: () => Promise<void>
}) {
  const [permisos, setPermisos] = useState<Record<string, PermisosModulo>>(
    Object.fromEntries(modulos.map((m) => [m.code, PERMISO_VACIO])),
  )
  const [guardandoPermisos, setGuardandoPermisos] = useState(false)
  const [miembroId, setMiembroId] = useState('')
  const [busyMiembro, setBusyMiembro] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const actuales = Object.fromEntries(
      modulos.map((m) => {
        const existente = grupo.permisos.find((p) => p.module_code === m.code)
        return [
          m.code,
          {
            ver: existente?.ver ?? 'ninguno',
            editar: existente?.editar ?? 'ninguno',
            crear: existente?.crear ?? 'ninguno',
            borrar: existente?.borrar ?? 'ninguno',
          },
        ]
      }),
    )
    setPermisos(actuales)
  }, [grupo, modulos])

  async function guardarPermisos() {
    setGuardandoPermisos(true)
    setError(null)
    try {
      await api.setPermisos(
        grupo.id,
        Object.entries(permisos).map(([module_code, valores]) => ({ module_code, ...valores })),
      )
      await onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardandoPermisos(false)
    }
  }

  const disponibles = usuarios.filter((u) => !grupo.miembros.some((m) => m.usuario_subject === u.id))

  async function anadirMiembro() {
    const usuario = usuarios.find((u) => u.id === miembroId)
    if (!usuario) return
    setBusyMiembro('nuevo')
    setError(null)
    try {
      await api.addMiembro(grupo.id, {
        usuario_subject: usuario.id,
        usuario_nombre: [usuario.firstName, usuario.lastName].filter(Boolean).join(' ') || usuario.username,
      })
      setMiembroId('')
      await onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusyMiembro(null)
    }
  }

  async function quitarMiembro(miembroGrupoId: string) {
    setBusyMiembro(miembroGrupoId)
    setError(null)
    try {
      await api.removeMiembro(grupo.id, miembroGrupoId)
      await onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusyMiembro(null)
    }
  }

  return (
    <ModalPantalla title={`Gestionar «${grupo.nombre}»`} onClose={onClose}>
      <ErrorNotice error={error} />

      <div className="form-section__title">Permisos por módulo</div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Módulo</th>
              {ACCIONES.map(([accion, etiqueta]) => (
                <th key={accion}>{etiqueta}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {modulos.map((m) => (
              <tr key={m.code}>
                <td>{m.name}</td>
                {ACCIONES.map(([accion]) => (
                  <td key={accion}>
                    <select
                      className="select"
                      value={permisos[m.code]?.[accion] ?? 'ninguno'}
                      onChange={(e) =>
                        setPermisos((actual) => ({
                          ...actual,
                          [m.code]: {
                            ...(actual[m.code] ?? PERMISO_VACIO),
                            [accion]: e.target.value as Alcance,
                          },
                        }))
                      }
                    >
                      {/* En «crear» no hay medias tintas: lo que das de alta
                          es tuyo, así que «sólo los míos» y «los de todos»
                          serían lo mismo y confundirían. */}
                      {(accion === 'crear'
                        ? (['ninguno', 'todos'] as Alcance[])
                        : (['ninguno', 'propios', 'todos'] as Alcance[])
                      ).map((a) => (
                        <option key={a} value={a}>
                          {accion === 'crear'
                            ? a === 'ninguno'
                              ? 'No'
                              : 'Sí'
                            : ETIQUETA_ALCANCE[a]}
                        </option>
                      ))}
                    </select>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="form-actions" style={{ border: 'none', background: 'none', padding: 'var(--sp-4) 0' }}>
        <button className="btn btn--primary" disabled={guardandoPermisos} onClick={() => void guardarPermisos()}>
          {!guardandoPermisos && <Save size={16} aria-hidden="true" />}
          {guardandoPermisos ? 'Guardando…' : 'Guardar permisos'}
        </button>
      </div>

      <h3 style={{ fontSize: 'var(--fs-lg)', fontWeight: 650, margin: 'var(--sp-4) 0 var(--sp-2)' }}>
        Miembros
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)', marginBottom: 'var(--sp-3)' }}>
        {grupo.miembros.map((m) => (
          <div
            key={m.id}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', maxWidth: 360 }}
          >
            <span>{m.usuario_nombre}</span>
            <button
              className="btn btn--sm"
              disabled={busyMiembro === m.id}
              onClick={() => void quitarMiembro(m.id)}
            >
              <UserMinus size={14} aria-hidden="true" />
              Quitar
            </button>
          </div>
        ))}
        {grupo.miembros.length === 0 && <span className="muted">Sin miembros</span>}
      </div>
      <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
        <select className="select" value={miembroId} onChange={(e) => setMiembroId(e.target.value)}>
          <option value="">Elegir usuario…</option>
          {disponibles.map((u) => (
            <option key={u.id} value={u.id}>
              {u.username}
            </option>
          ))}
        </select>
        <button
          className="btn btn--sm"
          disabled={!miembroId || busyMiembro === 'nuevo'}
          onClick={() => void anadirMiembro()}
        >
          <UserPlus size={14} aria-hidden="true" />
          Añadir
        </button>
      </div>

      <h3 style={{ fontSize: 'var(--fs-lg)', fontWeight: 650, margin: 'var(--sp-5) 0 var(--sp-2)' }}>
        Notificaciones
      </h3>
      <AvisosDeDestinatario grupoId={grupo.id} />
    </ModalPantalla>
  )
}
