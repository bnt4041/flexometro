import { useCallback, useEffect, useState } from 'react'
import { Check, Globe, Search, Send, Unlink, X } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal } from '../components/ui'
import { api } from '../lib/api'
import type { OrganizacionPublica, PerfilPlexo, VinculoPlexo } from '../lib/api'
import { useToast } from '../toast'

/** Universo Plexo: buscarse y conectar con otras organizaciones.
 *
 *  Esta primera pieza solo establece el vínculo — invitación, aceptación,
 *  ruptura. Todavía no mueve ningún documento de negocio entre las dos
 *  organizaciones; eso es la pieza siguiente, sobre esta base. */
export function Plexo() {
  const { notificar } = useToast()
  const [perfil, setPerfil] = useState<PerfilPlexo | null>(null)
  const [vinculos, setVinculos] = useState<VinculoPlexo[]>([])
  const [consulta, setConsulta] = useState('')
  const [resultados, setResultados] = useState<OrganizacionPublica[] | null>(null)
  const [invitando, setInvitando] = useState<OrganizacionPublica | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const [p, v] = await Promise.all([api.plexo.perfil(), api.plexo.vinculos.list()])
      setPerfil(p)
      setVinculos(v)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function alternarVisible(visible: boolean) {
    setOcupado(true)
    try {
      setPerfil(await api.plexo.fijarVisible(visible))
      notificar(visible ? 'Ya te pueden encontrar en el universo Plexo' : 'Ya no apareces en las búsquedas')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  async function buscar() {
    if (!consulta.trim()) {
      setResultados(null)
      return
    }
    try {
      setResultados(await api.plexo.buscar(consulta))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function invitar(mensaje: string) {
    if (!invitando) return
    setOcupado(true)
    try {
      await api.plexo.vinculos.invitar(invitando.id, mensaje || undefined)
      setInvitando(null)
      setResultados(null)
      setConsulta('')
      await cargar()
      notificar(`Invitación enviada a ${invitando.name}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  async function responder(v: VinculoPlexo, accion: 'aceptar' | 'rechazar' | 'revocar') {
    setOcupado(true)
    try {
      await api.plexo.vinculos[accion](v.id)
      await cargar()
      notificar(
        accion === 'aceptar'
          ? `Conectado con ${v.otra_organizacion.name}`
          : accion === 'rechazar'
            ? 'Invitación rechazada'
            : 'Desconectado',
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  const pendientesRecibidas = vinculos.filter((v) => v.estado === 'pendiente' && !v.soy_quien_invito)
  const pendientesEnviadas = vinculos.filter((v) => v.estado === 'pendiente' && v.soy_quien_invito)
  const conectadas = vinculos.filter((v) => v.estado === 'aceptado')

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">
            <Globe size={20} aria-hidden="true" style={{ verticalAlign: 'text-bottom', marginRight: 'var(--sp-2)' }} />
            Universo Plexo
          </h1>
          <p className="page-lead">
            Encuentra otras organizaciones y conecta con ellas para colaborar. De
            momento esto solo establece el vínculo: no comparte ningún dato de
            negocio todavía.
          </p>
        </div>
      </div>

      <ErrorNotice error={error} />

      <section className="form-section">
        <h2 className="form-section__title">Tu visibilidad</h2>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={perfil?.visible ?? false}
            disabled={ocupado || !perfil}
            onChange={(e) => void alternarVisible(e.target.checked)}
          />
          Aparecer en el universo Plexo, para que otras organizaciones me puedan
          encontrar e invitar a conectar.
        </label>
        <p className="muted">
          Apagado no te impide buscar ni invitar tú: solo decide si los demás
          pueden encontrarte a ti.
        </p>
      </section>

      <section className="form-section">
        <h2 className="form-section__title">Buscar organizaciones</h2>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <input
            className="input"
            value={consulta}
            placeholder="Nombre o CIF…"
            onChange={(e) => setConsulta(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void buscar()}
          />
          <button type="button" className="btn" onClick={() => void buscar()}>
            <Search size={16} aria-hidden="true" /> Buscar
          </button>
        </div>
        {resultados !== null && (
          <div className="table-wrap" style={{ marginTop: 'var(--sp-3)' }}>
            {resultados.length === 0 ? (
              <p className="muted">
                Nada. Solo aparecen organizaciones que han activado su
                visibilidad.
              </p>
            ) : (
              <table className="table">
                <tbody>
                  {resultados.map((o) => (
                    <tr key={o.id}>
                      <td>{o.name}</td>
                      <td className="muted">{o.cif ?? '—'}</td>
                      <td style={{ textAlign: 'right' }}>
                        <button
                          type="button"
                          className="btn btn--sm btn--primary"
                          onClick={() => setInvitando(o)}
                        >
                          <Send size={14} aria-hidden="true" /> Invitar a conectar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>

      {pendientesRecibidas.length > 0 && (
        <section className="form-section">
          <h2 className="form-section__title">Invitaciones recibidas</h2>
          <ul className="lista">
            {pendientesRecibidas.map((v) => (
              <li key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
                <div style={{ flex: 1 }}>
                  <strong>{v.otra_organizacion.name}</strong>
                  {v.mensaje && <p className="muted">«{v.mensaje}»</p>}
                </div>
                <button
                  type="button"
                  className="btn btn--sm btn--primary"
                  disabled={ocupado}
                  onClick={() => void responder(v, 'aceptar')}
                >
                  <Check size={14} aria-hidden="true" /> Aceptar
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={ocupado}
                  onClick={() => void responder(v, 'rechazar')}
                >
                  <X size={14} aria-hidden="true" /> Rechazar
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {pendientesEnviadas.length > 0 && (
        <section className="form-section">
          <h2 className="form-section__title">Invitaciones enviadas</h2>
          <ul className="lista">
            {pendientesEnviadas.map((v) => (
              <li key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
                <div style={{ flex: 1 }}>
                  <strong>{v.otra_organizacion.name}</strong>
                  <span className="muted"> · esperando respuesta</span>
                </div>
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={ocupado}
                  onClick={() => void responder(v, 'revocar')}
                >
                  Retirar
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="form-section">
        <h2 className="form-section__title">Conectadas</h2>
        {conectadas.length === 0 ? (
          <EmptyState title="Todavía sin conexiones">
            Busca una organización arriba y mándale una invitación.
          </EmptyState>
        ) : (
          <ul className="lista">
            {conectadas.map((v) => (
              <li key={v.id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
                <div style={{ flex: 1 }}>
                  <strong>{v.otra_organizacion.name}</strong>
                  <span className="muted"> · {v.otra_organizacion.cif ?? 'sin CIF'}</span>
                </div>
                <button
                  type="button"
                  className="btn btn--sm btn--danger"
                  disabled={ocupado}
                  onClick={() => void responder(v, 'revocar')}
                >
                  <Unlink size={14} aria-hidden="true" /> Desconectar
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {invitando && (
        <Modal title={`Invitar a ${invitando.name}`} onClose={() => setInvitando(null)}>
          <InvitarForm onCancelar={() => setInvitando(null)} onEnviar={invitar} ocupado={ocupado} />
        </Modal>
      )}
    </div>
  )
}

function InvitarForm({
  onCancelar,
  onEnviar,
  ocupado,
}: {
  onCancelar: () => void
  onEnviar: (mensaje: string) => void
  ocupado: boolean
}) {
  const [mensaje, setMensaje] = useState('')
  return (
    <>
      <Field label="Mensaje (opcional)">
        <textarea
          className="input"
          rows={3}
          value={mensaje}
          placeholder="Por ejemplo: para qué te gustaría colaborar"
          onChange={(e) => setMensaje(e.target.value)}
        />
      </Field>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCancelar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={ocupado}
          onClick={() => onEnviar(mensaje)}
        >
          <Send size={16} aria-hidden="true" /> Enviar invitación
        </button>
      </div>
    </>
  )
}
