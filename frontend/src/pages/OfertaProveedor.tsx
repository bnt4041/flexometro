import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ChevronDown, ChevronRight, Send, Sparkles } from 'lucide-react'

import { DescompuestoOfertaTabla } from '../components/DescompuestoOfertaTabla'
import { MedicionesOferta } from '../components/MedicionesOferta'
import { formatoImporte } from '../components/ui'

// La versión para fondo claro: esta página es una tarjeta blanca. El
// `logo-sobre-oscuro-recorte.png` que había aquí está recortado contra un
// fondo oscuro y sobre blanco se ve como un garabato.
import logo from '../assets/logo.png'
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
  /** Qué línea tiene el detalle desplegado, y en qué pestaña. */
  const [detalle, setDetalle] = useState<{ lineaId: string; pestana: 'medicion' | 'precio' } | null>(
    null,
  )
  const [leyendoIA, setLeyendoIA] = useState(false)
  const [avisoIA, setAvisoIA] = useState<string | null>(null)
  const ficheroIA = useRef<HTMLInputElement>(null)

  async function leerConIA(fichero: File) {
    setLeyendoIA(true)
    setAvisoIA(null)
    setError(null)
    try {
      const resultado = await apiPublico.leerDocumentoIA(token, fichero)
      setSeparata(resultado.separata)
      setAvisoIA(resultado.mensaje)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLeyendoIA(false)
      if (ficheroIA.current) ficheroIA.current.value = ''
    }
  }

  // Agrupado por capítulo para que se lea como un presupuesto y no como una
  // lista plana. Las líneas ya vienen ordenadas por capítulo del servidor.
  const porCapitulo = useMemo(() => {
    const grupos: { capitulo: string; lineas: LineaSeparata[] }[] = []
    for (const linea of separata?.lineas ?? []) {
      const nombre = linea.capitulo_resumen || 'Sin capítulo'
      const ultimo = grupos[grupos.length - 1]
      if (ultimo && ultimo.capitulo === nombre) ultimo.lineas.push(linea)
      else grupos.push({ capitulo: nombre, lineas: [linea] })
    }
    return grupos
  }, [separata])

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
    <div className="separata">
      <div className="separata__caja">
        <img src={logo} alt="Flexómetro" className="separata__logo" />

        {cargando && <p className="muted">Cargando…</p>}

        {!cargando && error && !separata && <ErrorNotice error={error} />}

        {mensajeFinal && <div className="notice notice--ok">{mensajeFinal}</div>}

        {!cargando && separata && !mensajeFinal && (
          <>
            <p className="muted" style={{ marginBottom: 0 }}>
              {separata.emisor} pide precio a {separata.proveedor}
            </p>
            <h1 className="separata__titulo">{separata.titulo}</h1>
            <p className="table__code" style={{ marginBottom: 'var(--sp-4)' }}>
              Solicitud de precios {separata.codigo}
            </p>

            {/* De qué obra se trata: sin esto el proveedor no puede cotizar
                (no sabe ni dónde tendría que ir). */}
            <div className="separata__obra">
              <div>
                <div className="barra-acciones__etiqueta">Obra</div>
                <div>{separata.obra || <span className="muted">—</span>}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Emplazamiento</div>
                <div>{separata.emplazamiento ?? <span className="muted">—</span>}</div>
              </div>
              {separata.cliente && (
                <div>
                  <div className="barra-acciones__etiqueta">Cliente</div>
                  <div>{separata.cliente}</div>
                </div>
              )}
              {separata.tipo_obra && (
                <div>
                  <div className="barra-acciones__etiqueta">Tipo de obra</div>
                  <div>{separata.tipo_obra}</div>
                </div>
              )}
              <div>
                <div className="barra-acciones__etiqueta">Fecha límite</div>
                <div>
                  {separata.fecha_limite ?? <span className="muted">sin fecha</span>}
                </div>
              </div>
            </div>

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

            {!soloLectura && (
              <div className="separata__ia">
                <input
                  ref={ficheroIA}
                  type="file"
                  accept=".pdf,.xlsx,.xlsm,.csv,.txt"
                  hidden
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) void leerConIA(f)
                  }}
                />
                <button
                  className="btn"
                  disabled={leyendoIA}
                  onClick={() => ficheroIA.current?.click()}
                >
                  <Sparkles size={16} aria-hidden="true" />
                  {leyendoIA ? 'Leyendo…' : 'Rellenar desde mi hoja de precios'}
                </button>
                <span className="muted">
                  Sube tu PDF, Excel o CSV y se rellenan los precios que se reconozcan. No te
                  cuesta nada: lo paga quien te ha pedido la oferta.
                </span>
              </div>
            )}

            {avisoIA && (
              <div className="notice" style={{ marginBottom: 'var(--sp-4)' }}>
                {avisoIA}
              </div>
            )}

            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th />
                    <th>Descripción</th>
                    <th>Unidad</th>
                    <th>Medición</th>
                    <th>Precio unitario</th>
                    <th>Importe</th>
                    <th>Observaciones</th>
                  </tr>
                </thead>
                <tbody>
                  {porCapitulo.map(({ capitulo, lineas }) => (
                    <Fragment key={capitulo}>
                      <tr className="separata__capitulo">
                        <td colSpan={7}>{capitulo}</td>
                      </tr>
                      {lineas.map((l) => {
                        const medida = l.medicion_proveedor ?? l.medicion
                        const importe =
                          l.precio_ofertado != null
                            ? Number(medida) * Number(l.precio_ofertado)
                            : null
                        return (
                          <Fragment key={l.id}>
                            <tr>
                              <td>
                                <button
                                  className="rejilla__plegar"
                                  aria-label={
                                    detalle?.lineaId === l.id ? 'Ocultar el detalle' : 'Detallar'
                                  }
                                  onClick={() =>
                                    setDetalle(
                                      detalle?.lineaId === l.id
                                        ? null
                                        : { lineaId: l.id, pestana: 'medicion' },
                                    )
                                  }
                                >
                                  {detalle?.lineaId === l.id ? (
                                    <ChevronDown size={14} aria-hidden="true" />
                                  ) : (
                                    <ChevronRight size={14} aria-hidden="true" />
                                  )}
                                </button>
                              </td>
                              <td>
                                {l.codigo && <span className="table__code">{l.codigo} </span>}
                                {l.resumen}
                                {l.texto && (
                                  // El texto de una partida viene de un editor
                                  // enriquecido, así que es HTML. El servidor lo
                                  // sanea con lista blanca al guardarlo y otra
                                  // vez al servirlo aquí (ver `publico_router`).
                                  <div
                                    className="muted separata__texto"
                                    dangerouslySetInnerHTML={{ __html: l.texto }}
                                  />
                                )}
                              </td>
                              <td>{l.unidad}</td>
                              <td className="table__num">
                                {l.medicion_proveedor !== null ? (
                                  <>
                                    <strong>{l.medicion_proveedor}</strong>
                                    <div className="muted">pedida: {l.medicion}</div>
                                  </>
                                ) : (
                                  l.medicion
                                )}
                              </td>
                              <td>
                                {l.descompuesto.length > 0 ? (
                                  // Con desglose, el precio es la suma de sus
                                  // componentes: se enseña, no se teclea.
                                  <span className="table__num" title="Sale de tu desglose">
                                    {l.precio_ofertado}
                                  </span>
                                ) : (
                                  <input
                                    className="input"
                                    type="number"
                                    min={0}
                                    step="0.01"
                                    disabled={soloLectura}
                                    value={l.precio_ofertado ?? ''}
                                    onChange={(e) =>
                                      actualizarLinea(l.id, {
                                        precio_ofertado: e.target.value || null,
                                      })
                                    }
                                    style={{ width: '8rem' }}
                                  />
                                )}
                              </td>
                              <td className="table__num">
                                {importe !== null ? formatoImporte(importe) : '—'}
                              </td>
                              <td>
                                <input
                                  className="input"
                                  type="text"
                                  disabled={soloLectura}
                                  value={l.observaciones_proveedor ?? ''}
                                  onChange={(e) =>
                                    actualizarLinea(l.id, {
                                      observaciones_proveedor: e.target.value || null,
                                    })
                                  }
                                />
                              </td>
                            </tr>
                            {detalle?.lineaId === l.id && (
                              <tr>
                                <td />
                                <td colSpan={6}>
                                  <div className="pestanas">
                                    <button
                                      className={
                                        detalle.pestana === 'medicion'
                                          ? 'pestanas__item is-activa'
                                          : 'pestanas__item'
                                      }
                                      onClick={() =>
                                        setDetalle({ lineaId: l.id, pestana: 'medicion' })
                                      }
                                    >
                                      Medición
                                      {l.mediciones.length > 0 && ` (${l.mediciones.length})`}
                                    </button>
                                    <button
                                      className={
                                        detalle.pestana === 'precio'
                                          ? 'pestanas__item is-activa'
                                          : 'pestanas__item'
                                      }
                                      onClick={() =>
                                        setDetalle({ lineaId: l.id, pestana: 'precio' })
                                      }
                                    >
                                      Desglose del precio
                                      {l.descompuesto.length > 0 && ` (${l.descompuesto.length})`}
                                    </button>
                                  </div>
                                  {detalle.pestana === 'medicion' ? (
                                    <MedicionesOferta
                                      token={token}
                                      linea={l}
                                      soloLectura={soloLectura}
                                      onSeparata={setSeparata}
                                    />
                                  ) : (
                                    <DescompuestoOfertaTabla
                                      token={token}
                                      linea={l}
                                      soloLectura={soloLectura}
                                      onSeparata={setSeparata}
                                    />
                                  )}
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        )
                      })}
                    </Fragment>
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
