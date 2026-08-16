import { api } from '../lib/api'
import { UsuariosYGruposCard } from './UsuariosYGruposCard'

/** Autoservicio del propio tenant: mismo componente que usa el panel de
 *  superadmin, apuntando a `/api/usuarios` y `/api/grupos` (la propia
 *  organización, gated por el rol `admin` en el backend) en vez de a
 *  `/api/admin/organizaciones/{id}/...`. */
export function UsuariosGrupos() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Usuarios y grupos</h1>
          <p className="page-lead">
            Quién puede entrar y qué puede ver o editar en cada módulo de tu organización.
          </p>
        </div>
      </div>

      <UsuariosYGruposCard api={api.usuariosYGrupos} />
    </>
  )
}
