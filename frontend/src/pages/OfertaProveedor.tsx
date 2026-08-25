import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Send } from 'lucide-react'

import logo from '../assets/logo-sobre-oscuro-recorte.png'
import { ErrorNotice } from '../components/ui'
import { apiPublico } from '../lib/api'
import type { LineaSeparata, Separata } from '../lib/api'

function formatoTamano(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** El único espacio de la aplicación sin sesión (ver plan «Solicitud de
 *  precios a proveedor», §2): quien entra llega desde un enlace de correo,
 *  no ha iniciado sesión ni la va a iniciar. No monta `WorkspaceProvider`
 *  (dispararía el arranque de Keycloak) ni `AppShell` — es una página suelta,
 *  con `apiPublico`, el único cliente que no manda `Authorization`. */
export function OfertaProveedor() {
  const { token = '' } = useParams()
  const [separata, setSeparata] = useState<Separata | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [mensajeFinal, setMensajeFinal] = useState<string | null>(null)

  useEffect(() => {
    apiPublico
      .verSeparata(token)
      .then((s) => setSeparata(s))
      .catch(() => setError('Este enlace no es válido o ha caducado. Consulta con quien te lo envió.'))
      .finally(() => setCargando(false))
  }, [token])

  function actualizarLinea(id: string, cambios: Partial<LineaSeparata>) {
    setSeparata((s) => (s ? { ...s, lineas: s.lineas.map((l) => (l.id === id ? { ...l, ...cambios } : l)) } : s))
  }

  async function guardar() {
    if (!separata) return
    setGuardando(true)
    setError(null)
    try {
      const actualizada = await apiPublico.guardarPrecios(
        token,
        separata.lineas.map((l) => ({
          id: l.id,
          precio_ofertado: l.precio_ofertado,
          observaciones_proveedor: l.observaciones_proveedor,
        })),
      )
      setSeparata(actualizada)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function enviar() {
    if (!separata) return
    setEnviando(true)
    setError(null)
    try {
      await apiPublico.guardarPrecios(
        token,
        separata.lineas.map((l) => ({
          id: l.id,
          precio_ofertado: l.precio_ofertado,
          observaciones_proveedor: l.observaciones_proveedor,
        })),
      )
      const resultado = await apiPublico.enviar(token)
      setMensajeFinal(resultado.mensaje)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  const hayAlMenosUnPrecio = separata?.lineas.some((l) => l.precio_ofertado) ?? false
  const soloLectura = separata != null && separata.estado !== 'enviada'

  return (
    <div className="portada-sesion" style={{ alignItems: 'flex-start', paddingTop: 'var(--sp-8)' }}>
      <div className="portada-sesion__caja" style={{ maxWidth: 920, width: '100%' }}>
        <img src={logo} alt="Flexómetro" style={{ height: 36, width: 'auto', marginBottom: 'var(--sp-4)' }} />

        {cargando && <p className="muted">Cargando…</p>}

        {!cargando && error && !separata && <ErrorNotice error={error} />}

        {mensajeFinal && <div className="notice notice--ok">{mensajeFinal}</div>}

        {!cargando && separata && !mensajeFinal && (
          <>
            <h1 style={{ marginBottom: 'var(--sp-1)' }}>Solicitud de precios {separata.codigo}</h1>
            <p className="muted" style={{ marginBottom: 'var(--sp-4)' }}>
              {separata.emisor} solicita precio a {separata.proveedor}
              {separata.fecha_limite ? ` — fecha límite: ${separata.fecha_limite}` : ''}
            </p>
            {separata.notas && (
              <p className="notice" style={{ marginBottom: 'var(--sp-4)' }}>
                {separata.notas}
              </p>
            )}

            {separata.documentos.length > 0 && (
              <div style={{ marginBottom: 'var(--sp-4)' }}>
                <p className="field__label">Documentos adjuntos</p>
                <ul>
                  {separata.documentos.map((d) => (
                    <li key={d.id}>
                      <a href={apiPublico.urlDocumento(token, d.id)} className="table__link">
                        {d.nombre_archivo}
                      </a>{' '}
                      <span className="muted">({formatoTamano(d.tamano_bytes)})</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {soloLectura && (
              <div className="notice notice--ok" style={{ marginBottom: 'var(--sp-4)' }}>
                Esta oferta ya se ha enviado. Consulta con {separata.emisor} si necesitas cambiar algo.
              </div>
            )}

            <ErrorNotice error={error} />

            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Capítulo</th>
                    <th>Código</th>
                    <th>Descripción</th>
                    <th>Unidad</th>
                    <th>Medición</th>
                    <th>Precio unitario</th>
                    <th>Observaciones</th>
                  </tr>
                </thead>
                <tbody>
                  {separata.lineas.map((l) => (
                    <tr key={l.id}>
                      <td className="muted">{l.capitulo_resumen}</td>
                      <td className="table__code">{l.codigo}</td>
                      <td>
                        {l.resumen}
                        {l.texto && (
                          <>
                            <br />
                            <span className="muted">{l.texto}</span>
                          </>
                        )}
                      </td>
                      <td>{l.unidad}</td>
                      <td className="table__num">{l.medicion}</td>
                      <td>
                        <input
                          className="input"
                          type="number"
                          min={0}
                          step="0.01"
                          disabled={soloLectura}
                          value={l.precio_ofertado ?? ''}
                          onChange={(e) =>
                            actualizarLinea(l.id, { precio_ofertado: e.target.value || null })
                          }
                          style={{ width: '9rem' }}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          type="text"
                          disabled={soloLectura}
                          value={l.observaciones_proveedor ?? ''}
                          onChange={(e) =>
                            actualizarLinea(l.id, { observaciones_proveedor: e.target.value || null })
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {!soloLectura && (
              <div className="form-actions" style={{ marginTop: 'var(--sp-4)' }}>
                <button className="btn" disabled={guardando || enviando} onClick={() => void guardar()}>
                  {guardando ? 'Guardando…' : 'Guardar borrador'}
                </button>
                <button
                  className="btn btn--primary"
                  disabled={!hayAlMenosUnPrecio || guardando || enviando}
                  onClick={() => void enviar()}
                >
                  <Send size={16} aria-hidden="true" />
                  {enviando ? 'Enviando…' : 'Enviar oferta'}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
