import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Check, Copy, Eraser, ExternalLink, Mail, X } from 'lucide-react'

import logo from '../assets/logo.png'
import { ErrorNotice } from '../components/ui'
import { VistaPdf } from '../components/VistaPdf'
import { apiPublico } from '../lib/api'
import type { CanalEnvio, DocumentoParaFirmar } from '../lib/api'
import { esNavegadorEmbebido } from '../lib/navegadorEmbebido'

/** Lo que se conserva entre visitas mientras la firma está a medias. */
type Borrador = { nombre?: string; dni?: string; firma?: string }

const claveBorrador = (token: string) => `firma:borrador:${token}`

/** El borrador se guarda porque el camino normal para firmar OBLIGA a salir
 *  de la página: el código de verificación llega por correo, así que hay que
 *  irse al buzón y volver. Si se vuelve a una página en blanco, hay que
 *  volver a dibujar la firma — y en el navegador incrustado de Gmail, que
 *  destruye la ventana al cambiar de aplicación, eso pasa casi siempre.
 *
 *  Va en `localStorage` y no en `sessionStorage` justamente por eso: la
 *  sesión de pestaña no sobrevive a ese viaje de ida y vuelta.
 *
 *  Nada de esto puede romper una firma: si el navegador va en modo privado o
 *  tiene la cuota llena, se pierde la comodidad y ya está. */
function leerBorrador(token: string): Borrador {
  try {
    return JSON.parse(localStorage.getItem(claveBorrador(token)) ?? '{}') as Borrador
  } catch {
    return {}
  }
}

function guardarBorrador(token: string, cambios: Borrador): void {
  try {
    localStorage.setItem(
      claveBorrador(token),
      JSON.stringify({ ...leerBorrador(token), ...cambios }),
    )
  } catch {
    /* Sin sitio o sin permiso: seguimos sin borrador. */
  }
}

function borrarBorrador(token: string): void {
  try {
    localStorage.removeItem(claveBorrador(token))
  } catch {
    /* Igual que arriba. */
  }
}

/** Firma de un documento por alguien de fuera, sin sesión — el segundo
 *  espacio sin cuenta de la aplicación, después de `/oferta/:token`.
 *
 *  Va fuera de `WorkspaceProvider` (ver `App.tsx`) para que el arranque de
 *  Keycloak no se dispare: quien entra aquí llega desde un correo, no tiene
 *  cuenta y no la va a tener.
 *
 *  La firma se dibuja a dedo o con el ratón sobre un `<canvas>` y viaja como
 *  PNG en data: URI. El servidor comprueba que lo sea de verdad antes de
 *  guardarla (ver `prl/firma.py`): ese campo acaba en el `src` de una imagen
 *  del PDF y de la ficha, así que aceptar cualquier cosa sería XSS. */
export function Firmar() {
  const { token = '' } = useParams()
  const lienzoRef = useRef<HTMLCanvasElement>(null)
  const dibujandoRef = useRef(false)
  const hayTrazoRef = useRef(false)

  const [documento, setDocumento] = useState<DocumentoParaFirmar | null>(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [resultado, setResultado] = useState<string | null>(null)
  const [nombre, setNombre] = useState('')
  const [dni, setDni] = useState('')
  const [motivo, setMotivo] = useState('')
  const [rechazando, setRechazando] = useState(false)
  // Segundo factor: el enlace por sí solo ya no basta para firmar.
  const [codigo, setCodigo] = useState('')
  const [codigoPedido, setCodigoPedido] = useState<string | null>(null)
  // Por dónde ha salido el código. No siempre es el correo: si el enlace vino
  // por WhatsApp, el código va por correo, y al revés.
  const [canalCodigo, setCanalCodigo] = useState<CanalEnvio[]>([])
  const [pidiendoCodigo, setPidiendoCodigo] = useState(false)
  const [enlaceCopiado, setEnlaceCopiado] = useState(false)
  // Se calcula una sola vez: el user-agent no cambia a mitad de visita.
  const [embebido] = useState(esNavegadorEmbebido)

  useEffect(() => {
    apiPublico.firma
      .ver(token)
      .then((d) => {
        setDocumento(d)
        // Lo tecleado en un intento anterior manda sobre el nombre de la
        // invitación: si lo corrigió, es que el de la invitación no le valía.
        const borrador = leerBorrador(token)
        setNombre(borrador.nombre || d.destinatario_nombre)
        if (borrador.dni) setDni(borrador.dni)
      })
      .catch(() =>
        setError('Este enlace no es válido, ya se ha usado o ha caducado.'),
      )
      .finally(() => setCargando(false))
  }, [token])

  /** El canvas se dimensiona a su tamaño real en píxeles para que el trazo no
   *  salga borroso ni desplazado respecto al dedo en pantallas con densidad
   *  alta. */
  const prepararLienzo = useCallback(() => {
    const canvas = lienzoRef.current
    if (!canvas) return
    const caja = canvas.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    canvas.width = caja.width * dpr
    canvas.height = caja.height * dpr
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.lineWidth = 2.5
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = '#111827'

    // Redimensionar un canvas lo vacía. Pasa al girar el móvil y al volver a
    // la página, así que hay que repintar lo que hubiera guardado o la firma
    // se esfuma sola.
    const guardada = leerBorrador(token).firma
    if (!guardada) return
    const imagen = new Image()
    imagen.onload = () => {
      ctx.drawImage(imagen, 0, 0, caja.width, caja.height)
      hayTrazoRef.current = true
    }
    imagen.src = guardada
  }, [token])

  useEffect(() => {
    if (documento?.estado === 'firmada' || documento?.estado === 'rechazada') return
    prepararLienzo()
    window.addEventListener('resize', prepararLienzo)
    return () => window.removeEventListener('resize', prepararLienzo)
  }, [prepararLienzo, documento?.estado])

  useEffect(() => {
    if (!documento) return
    guardarBorrador(token, { nombre, dni })
  }, [token, documento, nombre, dni])

  function posicion(e: React.PointerEvent<HTMLCanvasElement>) {
    const caja = e.currentTarget.getBoundingClientRect()
    return { x: e.clientX - caja.left, y: e.clientY - caja.top }
  }

  function empezar(e: React.PointerEvent<HTMLCanvasElement>) {
    e.currentTarget.setPointerCapture(e.pointerId)
    const ctx = lienzoRef.current?.getContext('2d')
    if (!ctx) return
    dibujandoRef.current = true
    hayTrazoRef.current = true
    const { x, y } = posicion(e)
    ctx.beginPath()
    ctx.moveTo(x, y)
  }

  function mover(e: React.PointerEvent<HTMLCanvasElement>) {
    if (!dibujandoRef.current) return
    const ctx = lienzoRef.current?.getContext('2d')
    if (!ctx) return
    const { x, y } = posicion(e)
    ctx.lineTo(x, y)
    ctx.stroke()
  }

  function terminar() {
    dibujandoRef.current = false
    if (hayTrazoRef.current) {
      const imagen = lienzoRef.current?.toDataURL('image/png')
      if (imagen) guardarBorrador(token, { firma: imagen })
    }
  }

  function limpiar() {
    const canvas = lienzoRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    hayTrazoRef.current = false
    guardarBorrador(token, { firma: undefined })
  }

  async function copiarEnlace() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setEnlaceCopiado(true)
      // Vuelve a su estado para que se pueda copiar otra vez sin recargar.
      window.setTimeout(() => setEnlaceCopiado(false), 4000)
    } catch {
      // Sin permiso de portapapeles queda el campo de texto de al lado, que
      // se selecciona entero al tocarlo.
      setError('No se ha podido copiar. Selecciona la dirección y cópiala a mano.')
    }
  }

  async function pedirCodigo() {
    setPidiendoCodigo(true)
    setError(null)
    try {
      const r = await apiPublico.firma.pedirCodigo(token)
      setCodigoPedido(r.destino)
      setCanalCodigo(r.canales)
      if (!r.enviado) {
        setError(
          `No se ha podido enviar el código a ${r.destino}. Avisa a quien te mandó el documento.`,
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setPidiendoCodigo(false)
    }
  }

  async function firmar() {
    if (!nombre.trim()) {
      setError('Escribe tu nombre y apellidos.')
      return
    }
    if (!hayTrazoRef.current) {
      setError('Dibuja tu firma en el recuadro antes de continuar.')
      return
    }
    if (codigo.trim().length < 4) {
      setError('Escribe el código de verificación que te hemos mandado.')
      return
    }
    setEnviando(true)
    setError(null)
    try {
      const imagen = lienzoRef.current?.toDataURL('image/png')
      if (!imagen) throw new Error('No se ha podido leer la firma')
      const r = await apiPublico.firma.firmar(token, {
        firmante_nombre: nombre,
        firmante_dni: dni || null,
        firma_imagen: imagen,
        codigo: codigo.trim(),
      })
      setResultado(r.mensaje)
      borrarBorrador(token)
      setDocumento((previo) => (previo ? { ...previo, estado: 'firmada' } : previo))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  async function rechazar() {
    if (!motivo.trim()) {
      setError('Indica por qué rechazas la firma.')
      return
    }
    setEnviando(true)
    setError(null)
    try {
      const r = await apiPublico.firma.rechazar(token, motivo)
      setResultado(r.mensaje)
      borrarBorrador(token)
      setDocumento((previo) => (previo ? { ...previo, estado: 'rechazada' } : previo))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  // Lo que decide si YO puedo firmar es mi propio estado: el documento
  // puede estar 'parcial' porque otro firmó y yo seguir teniendo que hacerlo.
  const cerrado = documento?.mi_estado === 'firmada' || documento?.mi_estado === 'rechazada'

  return (
    <div style={{ minHeight: '100vh', background: 'var(--c-bg)', padding: 'var(--sp-4)' }}>
      <div style={{ maxWidth: 760, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 'var(--sp-4)' }}>
          <img src={logo} alt="Flexómetro" style={{ height: 34, width: 'auto' }} />
        </div>

        {/* Cuando el correo se abre desde la app de Gmail, el enlace no va al
            navegador del móvil sino a una ventana de la propia app. Desde
            dentro no se puede salir por código, así que lo único honesto es
            avisar y poner el enlace a mano de quien firma. */}
        {embebido && !resultado && (
          <div
            className="notice"
            style={{
              marginBottom: 'var(--sp-4)',
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--sp-2)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
              <ExternalLink size={16} aria-hidden="true" />
              <strong>Estás en el navegador de otra aplicación</strong>
            </div>
            <p style={{ margin: 0, fontSize: '0.9em' }}>
              Puedes firmar aquí mismo, pero irá más fino en el navegador del móvil. Ábrelo con
              el menú <strong>⋮</strong> de arriba («Abrir en el navegador») o copia la dirección
              y pégala tú.
            </p>
            <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
              <input
                className="input"
                readOnly
                value={window.location.href}
                onFocus={(e) => e.currentTarget.select()}
                style={{ flex: '1 1 220px', fontSize: '0.85em' }}
              />
              <button type="button" className="btn btn--sm" onClick={() => void copiarEnlace()}>
                <Copy size={14} aria-hidden="true" /> {enlaceCopiado ? 'Copiado' : 'Copiar'}
              </button>
            </div>
          </div>
        )}

        {cargando && <p className="muted">Cargando el documento…</p>}
        <ErrorNotice error={error} />

        {documento && (
          <div className="card" style={{ padding: 'var(--sp-5)' }}>
            <h1 style={{ fontSize: '1.3rem', marginTop: 0 }}>{documento.titulo}</h1>
            <p className="muted" style={{ marginTop: 0 }}>
              Enviado por <strong>{documento.emisor}</strong> a {documento.destinatario_nombre}
            </p>
            {documento.otros_firmantes.length > 0 && (
              <p className="muted" style={{ marginTop: 0, fontSize: '0.9em' }}>
                Este documento lo firman también:{' '}
                {documento.otros_firmantes
                  .map(
                    (o) =>
                      `${o.nombre} (${
                        o.estado === 'firmada'
                          ? 'ya firmó'
                          : o.estado === 'rechazada'
                            ? 'rechazó'
                            : 'pendiente'
                      })`,
                  )
                  .join(', ')}
                .
              </p>
            )}

            {documento.origen === 'pdf' ? (
              /* El PDF se sirve por la ruta pública del token (la descarga
                 normal exige sesión) y se pinta con pdf.js: ver `VistaPdf`
                 para por qué no vale el visor del navegador. */
              <div style={{ margin: 'var(--sp-4) 0' }}>
                <VistaPdf url={apiPublico.firma.urlDocumento(token)} />
              </div>
            ) : (
              <div
                style={{
                  border: '1px solid var(--c-border)',
                  borderRadius: 8,
                  padding: 'var(--sp-4)',
                  margin: 'var(--sp-4) 0',
                  background: 'var(--c-surface)',
                }}
                // Saneado en el servidor al crear la solicitud (`sanear_html`):
                // el filtro vive ahí, no aquí, para que valga igual en el PDF.
                dangerouslySetInnerHTML={{ __html: documento.contenido_html }}
              />
            )}

            {resultado ? (
              <p className="notice notice--ok">{resultado}</p>
            ) : cerrado ? (
              <p className="notice notice--ok">
                Ya has {documento.mi_estado === 'firmada' ? 'firmado' : 'rechazado'} este documento.
                {documento.estado === 'parcial' && ' Faltan otros firmantes por hacerlo.'}
              </p>
            ) : (
              <>
                <div className="form-grid">
                  <div className="field field--doble">
                    <span className="field__label">Nombre y apellidos</span>
                    <input
                      className="input"
                      value={nombre}
                      onChange={(e) => setNombre(e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <span className="field__label">DNI / NIE (opcional)</span>
                    <input className="input" value={dni} onChange={(e) => setDni(e.target.value)} />
                  </div>
                </div>

                <div style={{ marginTop: 'var(--sp-4)' }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 'var(--sp-2)',
                    }}
                  >
                    <span className="field__label">Firma aquí</span>
                    <button type="button" className="btn btn--sm" onClick={limpiar}>
                      <Eraser size={14} aria-hidden="true" /> Borrar
                    </button>
                  </div>
                  <canvas
                    ref={lienzoRef}
                    onPointerDown={empezar}
                    onPointerMove={mover}
                    onPointerUp={terminar}
                    onPointerLeave={terminar}
                    style={{
                      width: '100%',
                      height: 180,
                      border: '2px dashed var(--c-border-strong)',
                      borderRadius: 8,
                      background: '#fff',
                      // Sin esto, arrastrar el dedo hace scroll de la página
                      // en vez de dibujar.
                      touchAction: 'none',
                      display: 'block',
                    }}
                  />
                </div>

                {/* Segundo factor. Va justo antes de los botones para que se
                    vea que es un paso obligatorio, no un extra opcional. */}
                <div
                  style={{
                    marginTop: 'var(--sp-4)',
                    padding: 'var(--sp-3)',
                    border: '1px solid var(--c-border)',
                    borderRadius: 'var(--radius)',
                    background: 'var(--c-surface-2)',
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 'var(--sp-2)' }}>
                    Verificación en dos pasos
                  </div>
                  {codigoPedido ? (
                    <>
                      <p className="muted" style={{ margin: '0 0 var(--sp-2)', fontSize: '0.9em' }}>
                        Te hemos mandado un código de 6 dígitos{' '}
                        {canalCodigo.includes('whatsapp') && canalCodigo.includes('email')
                          ? 'por WhatsApp y correo a '
                          : canalCodigo.includes('whatsapp')
                            ? 'por WhatsApp al '
                            : 'por correo a '}
                        <strong>{codigoPedido}</strong>. Caduca en 10 minutos. Puedes salir a
                        buscarlo tranquilo: tu firma y tus datos se quedan guardados en este
                        móvil.
                      </p>
                      <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                        <input
                          className="input"
                          value={codigo}
                          onChange={(e) => setCodigo(e.target.value.replace(/\D/g, '').slice(0, 6))}
                          placeholder="000000"
                          inputMode="numeric"
                          autoComplete="one-time-code"
                          style={{
                            maxWidth: 160,
                            fontSize: '1.3rem',
                            letterSpacing: '0.3em',
                            textAlign: 'center',
                          }}
                        />
                        <button
                          type="button"
                          className="btn btn--sm"
                          onClick={() => void pedirCodigo()}
                          disabled={pidiendoCodigo}
                        >
                          Reenviar
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <p className="muted" style={{ margin: '0 0 var(--sp-2)', fontSize: '0.9em' }}>
                        Para firmar hace falta un código de verificación. Te lo mandamos por un
                        canal distinto de aquel por el que te llegó este enlace: así queda
                        acreditado que eres tú quien firma, y no solo quien tiene el enlace.
                      </p>
                      <button
                        type="button"
                        className="btn"
                        onClick={() => void pedirCodigo()}
                        disabled={pidiendoCodigo}
                      >
                        <Mail size={16} aria-hidden="true" />{' '}
                        {pidiendoCodigo ? 'Enviando…' : 'Enviarme el código'}
                      </button>
                    </>
                  )}
                </div>

                <div
                  style={{
                    display: 'flex',
                    gap: 'var(--sp-3)',
                    justifyContent: 'flex-end',
                    marginTop: 'var(--sp-4)',
                    flexWrap: 'wrap',
                  }}
                >
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setRechazando((v) => !v)}
                    disabled={enviando}
                  >
                    <X size={16} aria-hidden="true" /> Rechazar
                  </button>
                  <button
                    type="button"
                    className="btn btn--primary"
                    onClick={firmar}
                    disabled={enviando || !codigoPedido}
                  >
                    <Check size={16} aria-hidden="true" /> {enviando ? 'Firmando…' : 'Firmar documento'}
                  </button>
                </div>

                {rechazando && (
                  <div style={{ marginTop: 'var(--sp-3)' }}>
                    <span className="field__label">Motivo del rechazo</span>
                    <textarea
                      className="input"
                      rows={3}
                      value={motivo}
                      onChange={(e) => setMotivo(e.target.value)}
                    />
                    <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--sp-2)' }}>
                      <button
                        type="button"
                        className="btn btn--danger"
                        onClick={rechazar}
                        disabled={enviando}
                      >
                        Confirmar rechazo
                      </button>
                    </div>
                  </div>
                )}

                <p className="muted" style={{ fontSize: '0.8em', marginTop: 'var(--sp-4)' }}>
                  Al firmar quedan registrados tu nombre, la fecha y hora, tu dirección IP y tu
                  navegador, como evidencia de la firma. Se trata de una firma electrónica simple:
                  no sustituye a una firma con certificado digital.
                </p>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
