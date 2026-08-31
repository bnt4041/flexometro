import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { BellOff, ChevronDown, LogOut, Star, StarOff, Trash2, User } from 'lucide-react'

import { ErrorNotice, Field, Modal } from '../components/ui'
import { api } from '../lib/api'
import type { Favorito, Perfil, PreferenciaAvisos } from '../lib/api'
import { useToast } from '../toast'

/** El rincón del usuario: sus favoritos, su perfil y salir.
 *
 *  Antes era el nombre suelto y un botón de salir. Los favoritos van aquí y
 *  no en la barra lateral porque son de cada uno, no del producto: la barra
 *  la manda el módulo activo, esto lo mandas tú. */
export function MenuUsuario({
  nombre,
  esAdmin,
  onSalir,
}: {
  nombre: string
  esAdmin: boolean
  onSalir: () => void
}) {
  const { notificar } = useToast()
  const navegar = useNavigate()
  const ubicacion = useLocation()
  const [abierto, setAbierto] = useState(false)
  const [favoritos, setFavoritos] = useState<Favorito[]>([])
  const [perfil, setPerfil] = useState(false)
  const cajaRef = useRef<HTMLDivElement>(null)

  const rutaActual = ubicacion.pathname + ubicacion.search
  const guardada = favoritos.find((f) => f.ruta === rutaActual)

  const cargar = useCallback(async () => {
    try {
      setFavoritos(await api.yo.favoritos.list())
    } catch {
      // Sin favoritos el menú sigue sirviendo para el perfil y para salir.
      setFavoritos([])
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  // Cerrar al pulsar fuera: un menú que se queda abierto tapando la pantalla
  // es peor que no tenerlo.
  useEffect(() => {
    if (!abierto) return
    const fuera = (e: MouseEvent) => {
      if (!cajaRef.current?.contains(e.target as Node)) setAbierto(false)
    }
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setAbierto(false)
    document.addEventListener('mousedown', fuera)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', fuera)
      document.removeEventListener('keydown', escape)
    }
  }, [abierto])

  async function alternarFavorito() {
    try {
      if (guardada) {
        await api.yo.favoritos.remove(guardada.id)
        notificar('Quitado de favoritos')
      } else {
        // El `h1` de la pantalla, que es literalmente su nombre en grande.
        // NO el título de la pestaña: es el mismo en toda la aplicación, así
        // que todos los favoritos acabarían llamándose «Flexómetro — ERP de
        // construcción» y no servirían para distinguir nada.
        const titulo = document.querySelector('h1')?.textContent?.trim()
        const etiqueta = (titulo || rutaActual).slice(0, 120)
        await api.yo.favoritos.guardar({ etiqueta, ruta: rutaActual })
        notificar('Guardado en favoritos')
      }
      await cargar()
    } catch (err) {
      notificar(err instanceof Error ? err.message : 'No se ha podido guardar', 'error')
    }
  }

  async function borrar(favorito: Favorito) {
    await api.yo.favoritos.remove(favorito.id).catch(() => undefined)
    await cargar()
  }

  return (
    <div ref={cajaRef} style={{ position: 'relative' }}>
      <button
        className="btn btn--sm"
        onClick={() => setAbierto((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={abierto}
      >
        <User size={14} aria-hidden="true" />
        {nombre}
        {esAdmin && <span className="badge">admin</span>}
        <ChevronDown size={13} aria-hidden="true" />
      </button>

      {abierto && (
        <div
          role="menu"
          className="card"
          style={{
            position: 'absolute',
            right: 0,
            top: 'calc(100% + 6px)',
            width: 280,
            zIndex: 60,
            padding: 'var(--sp-2)',
            boxShadow: 'var(--sombra-flotante, 0 8px 24px rgba(0,0,0,.18))',
          }}
        >
          <button
            className="btn btn--sm"
            style={{ width: '100%', justifyContent: 'flex-start' }}
            onClick={() => void alternarFavorito()}
          >
            {guardada ? <StarOff size={14} aria-hidden="true" /> : <Star size={14} aria-hidden="true" />}
            {guardada ? 'Quitar de favoritos' : 'Guardar esta página'}
          </button>

          <div
            className="muted"
            style={{ fontSize: '0.78em', textTransform: 'uppercase', margin: 'var(--sp-3) 0 4px 6px' }}
          >
            Favoritos
          </div>
          {favoritos.length === 0 ? (
            <p className="muted" style={{ fontSize: '0.85em', margin: '0 6px var(--sp-2)' }}>
              Todavía ninguno. Guarda las pantallas que uses a diario.
            </p>
          ) : (
            <div style={{ maxHeight: 220, overflowY: 'auto' }}>
              {favoritos.map((favorito) => (
                <div key={favorito.id} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <button
                    className="btn btn--sm"
                    style={{ flex: 1, justifyContent: 'flex-start', overflow: 'hidden' }}
                    onClick={() => {
                      navegar(favorito.ruta)
                      setAbierto(false)
                    }}
                    title={favorito.ruta}
                  >
                    <Star size={13} aria-hidden="true" />
                    <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                      {favorito.etiqueta}
                    </span>
                  </button>
                  <button
                    className="btn btn--sm"
                    aria-label={`Quitar ${favorito.etiqueta}`}
                    onClick={() => void borrar(favorito)}
                  >
                    <Trash2 size={12} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <hr style={{ border: 0, borderTop: '1px solid var(--c-border)', margin: 'var(--sp-2) 0' }} />

          <button
            className="btn btn--sm"
            style={{ width: '100%', justifyContent: 'flex-start' }}
            onClick={() => {
              setPerfil(true)
              setAbierto(false)
            }}
          >
            <User size={14} aria-hidden="true" /> Mi perfil
          </button>
          <button
            className="btn btn--sm btn--danger"
            style={{ width: '100%', justifyContent: 'flex-start', marginTop: 4 }}
            onClick={onSalir}
          >
            <LogOut size={14} aria-hidden="true" /> Salir
          </button>
        </div>
      )}

      {perfil && <MiPerfil onCerrar={() => setPerfil(false)} />}
    </div>
  )
}

function MiPerfil({ onCerrar }: { onCerrar: () => void }) {
  const { notificar } = useToast()
  const [perfil, setPerfil] = useState<Perfil | null>(null)
  const [avisos, setAvisos] = useState<PreferenciaAvisos | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.yo
      .perfil()
      .then(setPerfil)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
    // Las preferencias de aviso viven aquí: son lo único de las
    // notificaciones que decide uno mismo, y su sitio natural es su perfil.
    api.avisos.misPreferencias
      .get()
      .then(setAvisos)
      .catch(() => setAvisos(null))
  }, [])

  async function guardarAvisos() {
    if (!avisos) return
    try {
      setAvisos(await api.avisos.misPreferencias.update(avisos))
      notificar('Guardado')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Mi perfil" onClose={onCerrar}>
      <div className="form-section">
        <ErrorNotice error={error} />
        {!perfil ? (
          <p className="muted">Cargando…</p>
        ) : (
          <>
            <div className="form-grid">
              <Field label="Usuario">
                <input className="input" value={perfil.username} readOnly />
              </Field>
              <Field label="Nombre">
                <input className="input" value={perfil.nombre ?? '—'} readOnly />
              </Field>
              <Field ancho="doble" label="Correo">
                <input className="input" value={perfil.email ?? 'Sin correo en Keycloak'} readOnly />
              </Field>
              <Field label="Organización">
                <input className="input" value={perfil.organizacion ?? '—'} readOnly />
              </Field>
            </div>

            <div style={{ marginTop: 'var(--sp-3)' }}>
              <span className="field__label">Grupos</span>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                {perfil.grupos.length === 0 ? (
                  <span className="muted">Sin grupos. Tus permisos vienen solo de tus roles.</span>
                ) : (
                  perfil.grupos.map((g) => (
                    <span key={g.id} className="badge">
                      {g.nombre}
                    </span>
                  ))
                )}
                {perfil.roles.map((rol) => (
                  <span key={rol} className="badge badge--info">
                    {rol}
                  </span>
                ))}
              </div>
              <p className="muted" style={{ fontSize: '0.85em', marginTop: 6 }}>
                Los permisos se cambian desde Usuarios y grupos, no desde aquí.
              </p>
            </div>

            {avisos && (
              <>
                <div className="form-section__title" style={{ marginTop: 'var(--sp-4)' }}>
                  Mis avisos
                </div>
                <p className="form-section__note">
                  De qué te avisan se decide en tu ficha. Esto es lo que decides tú.
                </p>
                <div className="form-grid">
                  <Field ancho="doble" label="Mi móvil" hint="Para los avisos por WhatsApp">
                    <input
                      className="input"
                      type="tel"
                      placeholder="+34 600 11 22 33"
                      value={avisos.telefono ?? ''}
                      onChange={(e) => setAvisos({ ...avisos, telefono: e.target.value || null })}
                    />
                  </Field>
                </div>
                <label className="checkbox" style={{ display: 'block', marginTop: 'var(--sp-2)' }}>
                  <input
                    type="checkbox"
                    checked={avisos.silenciado}
                    onChange={(e) => setAvisos({ ...avisos, silenciado: e.target.checked })}
                  />
                  <span>
                    <BellOff size={13} aria-hidden="true" /> Silenciar correo y WhatsApp{' '}
                    <span className="muted" style={{ fontSize: '0.85em' }}>
                      — la campana se sigue llenando
                    </span>
                  </span>
                </label>
                <div className="form-actions">
                  <button className="btn btn--primary" onClick={() => void guardarAvisos()}>
                    Guardar mis avisos
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}
