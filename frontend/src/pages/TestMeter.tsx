import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Camera, Check, Loader2, MapPin, RotateCcw, Undo2, X } from 'lucide-react'
import * as THREE from 'three'

import logo from '../assets/logo.png'
import { ErrorNotice } from '../components/ui'
import { PlantaLevantamiento, areaDe, perimetroDe } from '../components/PlantaLevantamiento'
import type { PuntoPlanta } from '../components/PlantaLevantamiento'
import { CARACTERISTICA_CAMARA_XR, capturarFotogramaXR } from '../lib/camaraXR'
import { apiPublico } from '../lib/api'
import type { ProveedorVision, ResultadoMedicionIA, RevisionPlanta } from '../lib/api'

type Etapa = 'reconociendo' | 'listo' | 'levantando'

const NARANJA = 0xf59e0b
const NARANJA_CSS = '#f59e0b'
const VERDE = 0x22c55e

// `.btn` hereda `background: var(--c-surface)`, que en tema claro es un
// fondo casi blanco — combinado con el `color: '#fff'` que necesitan estos
// botones (van sobre el panel oscuro del plano, no sobre la página) salía
// texto blanco sobre botón blanco. Fondo oscuro translúcido propio en vez de
// heredar el del tema, para que se lea igual en claro y en oscuro.
const BOTON_SOBRE_OSCURO: CSSProperties = {
  color: '#fff',
  background: 'rgba(255,255,255,0.12)',
  borderColor: 'rgba(255,255,255,0.35)',
}

function formatoCota(metros: number): string {
  return metros < 1 ? `${Math.round(metros * 100)} cm` : `${metros.toFixed(2)} m`
}

/** Levantamiento de planta con AR + IA (`/testmeter`, sin sesión ni
 *  organización — ver `App.tsx`).
 *
 *  El reparto de trabajo entre las dos piezas no es arbitrario, es lo que
 *  cada una puede hacer bien:
 *
 *  - **El AR (WebXR `immersive-ar` + `hit-test`) pone la geometría.** Para
 *    encadenar esquinas en un perímetro hacen falta COORDENADAS
 *    consistentes entre sí, y eso exige saber dónde está el móvil en cada
 *    momento — es seguimiento de posición 3D, no algo que se pueda deducir
 *    de fotos sueltas. Cada esquina marcada es un punto 3D real; descartar
 *    su altura (`y`) da directamente la vista en planta.
 *  - **La IA pone la semántica.** Antes de empezar reconoce el espacio y sus
 *    elementos (puerta, ventana, hueco...), que es lo que convierte una
 *    poligonal en un plano legible y lo que el AR no sabe hacer.
 *
 *  Pantalla partida: arriba la cámara con el retículo, abajo la planta que se
 *  va dibujando, siempre autoencuadrada. Solo Chrome/Android con ARCore. */
export function TestMeter() {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const contenedorRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const sesionRef = useRef<XRSession | null>(null)

  const puntosRef = useRef<THREE.Vector3[]>([])
  const cerradoRef = useRef(false)
  const ultimaPoseRef = useRef<THREE.Vector3 | null>(null)
  const marcarRef = useRef<(() => void) | null>(null)
  const redibujarEscenaRef = useRef<(() => void) | null>(null)
  /** Una foto por esquina marcada, en orden. Se llenan durante la sesión y se
   *  mandan enteras al cerrar el perímetro. */
  const fotosRef = useRef<Blob[]>([])
  /** La captura tiene que ocurrir DENTRO del bucle de render (la textura de
   *  la cámara solo vale en ese frame), así que marcar una esquina no captura
   *  directamente: deja este aviso y el bucle lo atiende en el frame
   *  siguiente. Ver `camaraXR.ts`. */
  const capturaPendienteRef = useRef(false)

  const [soportado, setSoportado] = useState<boolean | null>(null)
  const [etapa, setEtapa] = useState<Etapa>('listo')
  const [error, setError] = useState<string | null>(null)
  const [reconocido, setReconocido] = useState<ResultadoMedicionIA | null>(null)
  const [proveedor, setProveedor] = useState<ProveedorVision>('deepseek')

  const [puntos, setPuntos] = useState<PuntoPlanta[]>([])
  const [cerrado, setCerrado] = useState(false)
  const [posicionActual, setPosicionActual] = useState<PuntoPlanta | null>(null)
  const [superficie, setSuperficie] = useState(false)
  const [nFotos, setNFotos] = useState(0)
  const [revisando, setRevisando] = useState(false)
  const [revision, setRevision] = useState<RevisionPlanta | null>(null)

  useEffect(() => {
    const xr = (navigator as Navigator & { xr?: XRSystem }).xr
    if (!xr) {
      setSoportado(false)
      return
    }
    xr.isSessionSupported('immersive-ar')
      .then(setSoportado)
      .catch(() => setSoportado(false))
  }, [])

  // Cámara de previsualización, solo para la fase de reconocimiento: dentro
  // de la sesión de AR el vídeo lo pinta el propio WebXR.
  useEffect(() => {
    if (etapa === 'levantando') return
    let cancelado = false
    navigator.mediaDevices
      ?.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      .then((stream) => {
        if (cancelado) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
      })
      .catch(() => {
        if (!cancelado) setError('No se ha podido abrir la cámara (¿permiso denegado?).')
      })
    return () => {
      cancelado = true
      streamRef.current?.getTracks().forEach((t) => t.stop())
    }
  }, [etapa])

  /** Paso previo: una foto para que la IA diga qué espacio es y qué hay en
   *  él. No fija la escala (de eso ya se encarga el AR, que mide en metros
   *  reales) — aporta el nombre de las cosas. */
  async function reconocerEspacio() {
    const video = videoRef.current
    if (!video || !video.videoWidth) return
    setEtapa('reconociendo')
    setError(null)
    const captura = document.createElement('canvas')
    captura.width = video.videoWidth
    captura.height = video.videoHeight
    captura.getContext('2d')?.drawImage(video, 0, 0)
    const blob = await new Promise<Blob | null>((r) => captura.toBlob(r, 'image/jpeg', 0.9))
    if (!blob) {
      setEtapa('listo')
      return
    }
    try {
      setReconocido(await apiPublico.testmeter.medirFoto(blob, proveedor))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEtapa('listo')
    }
  }

  function sincronizarPlanta() {
    setPuntos(puntosRef.current.map((p) => ({ x: p.x, z: p.z })))
    setCerrado(cerradoRef.current)
  }

  async function iniciarLevantamiento() {
    setError(null)
    const xr = (navigator as Navigator & { xr?: XRSystem }).xr
    if (!xr || !contenedorRef.current || !overlayRef.current) return

    let sesion: XRSession
    try {
      sesion = await xr.requestSession('immersive-ar', {
        requiredFeatures: ['hit-test'],
        // `camera-access` va como OPCIONAL a propósito: si el dispositivo no
        // lo soporta (Chrome Android 107+ es el único que lo trae), se sigue
        // pudiendo levantar la planta — solo que sin fotos, y por tanto sin
        // la revisión de elementos al cerrar.
        optionalFeatures: ['dom-overlay', CARACTERISTICA_CAMARA_XR],
        domOverlay: { root: overlayRef.current },
      })
    } catch (err) {
      setError(
        err instanceof Error ? `No se ha podido iniciar AR: ${err.message}` : 'No se ha podido iniciar AR.',
      )
      return
    }
    sesionRef.current = sesion
    streamRef.current?.getTracks().forEach((t) => t.stop())

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setPixelRatio(window.devicePixelRatio)
    renderer.setSize(window.innerWidth, window.innerHeight)
    renderer.xr.enabled = true
    // Three.js pide 'local-floor' por defecto (detección de suelo, opcional
    // en el estándar y no disponible en todos los móviles); 'local' sí es de
    // soporte obligado en cualquier sesión inmersiva.
    renderer.xr.setReferenceSpaceType('local')
    contenedorRef.current.appendChild(renderer.domElement)

    const scene = new THREE.Scene()
    const camara3d = new THREE.PerspectiveCamera()
    scene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 3))

    const reticulo = new THREE.Mesh()
    reticulo.add(
      new THREE.Mesh(
        new THREE.RingGeometry(0.05, 0.065, 40).rotateX(-Math.PI / 2),
        new THREE.MeshBasicMaterial({ color: VERDE }),
      ),
      new THREE.Mesh(
        new THREE.CircleGeometry(0.012, 24).rotateX(-Math.PI / 2),
        new THREE.MeshBasicMaterial({ color: VERDE }),
      ),
    )
    reticulo.matrixAutoUpdate = false
    reticulo.visible = false
    scene.add(reticulo)

    // Toda la poligonal marcada hasta ahora, redibujada de cero en cada
    // cambio: son pocos vértices y así no hay que llevar la cuenta de qué
    // objeto corresponde a qué punto al deshacer.
    const dibujo = new THREE.Group()
    scene.add(dibujo)
    function redibujarEscena() {
      dibujo.clear()
      const pts = puntosRef.current
      pts.forEach((p) => {
        const esfera = new THREE.Mesh(
          new THREE.SphereGeometry(0.02, 16, 16),
          new THREE.MeshBasicMaterial({ color: NARANJA }),
        )
        esfera.position.copy(p)
        dibujo.add(esfera)
      })
      if (pts.length >= 2) {
        const recorrido = cerradoRef.current ? [...pts, pts[0]] : pts
        dibujo.add(
          new THREE.Line(
            new THREE.BufferGeometry().setFromPoints(recorrido),
            new THREE.LineBasicMaterial({ color: NARANJA }),
          ),
        )
      }
    }
    redibujarEscenaRef.current = redibujarEscena

    try {
      await renderer.xr.setSession(sesion)
    } catch (err) {
      setError(
        err instanceof Error
          ? `No se ha podido activar el render de AR: ${err.message}`
          : 'No se ha podido activar el render de AR.',
      )
      sesion.end()
      return
    }

    setEtapa('levantando')

    function marcar() {
      const pos = ultimaPoseRef.current
      if (!pos || cerradoRef.current) {
        if (!pos) {
          setError('Aún no hay superficie detectada. Apunta al suelo hasta que el retículo se ponga verde.')
        }
        return
      }
      setError(null)
      puntosRef.current = [...puntosRef.current, pos.clone()]
      // No se captura aquí: la textura de la cámara solo es válida dentro del
      // callback de animación, así que se deja pedido para el próximo frame.
      capturaPendienteRef.current = true
      redibujarEscena()
      sincronizarPlanta()
    }
    marcarRef.current = marcar
    sesion.addEventListener('select', marcar)

    function alTerminar() {
      sesion.removeEventListener('select', marcar)
      renderer.setAnimationLoop(null)
      renderer.dispose()
      contenedorRef.current?.removeChild(renderer.domElement)
      sesionRef.current = null
      marcarRef.current = null
      redibujarEscenaRef.current = null
      ultimaPoseRef.current = null
      setEtapa('listo')
      setSuperficie(false)
      setPosicionActual(null)
    }
    sesion.addEventListener('end', alTerminar)

    let fuentePedida = false
    let fuenteHitTest: XRHitTestSource | null = null
    let frames = 0

    // Andamiaje de `camera-access`: el binding y el framebuffer de lectura se
    // crean una sola vez y se reutilizan en cada captura (ver `camaraXR.ts`).
    const gl = renderer.getContext()
    const hayCamaraXR = sesion.enabledFeatures?.includes(CARACTERISTICA_CAMARA_XR) ?? false
    const binding = hayCamaraXR ? new XRWebGLBinding(sesion, gl) : null
    const framebufferLectura = hayCamaraXR ? gl.createFramebuffer() : null

    renderer.setAnimationLoop((_t, frame) => {
      if (!frame) return
      const referencia = renderer.xr.getReferenceSpace()
      if (!referencia) return

      // Captura pedida al marcar la última esquina. Se hace antes de pintar
      // la escena para no arrastrar el cambio de framebuffer al render.
      if (capturaPendienteRef.current) {
        capturaPendienteRef.current = false
        if (binding && framebufferLectura) {
          capturarFotogramaXR(frame, binding, gl, referencia, framebufferLectura)
            .then((foto) => {
              if (foto) {
                fotosRef.current = [...fotosRef.current, foto]
                setNFotos(fotosRef.current.length)
              }
            })
            .catch(() => {
              /* Una foto perdida no debe cortar el levantamiento: la planta
                 se sigue midiendo igual, solo habrá menos material para la
                 revisión final. */
            })
        }
      }

      // El hit-test source se pide DENTRO del bucle (patrón de los ejemplos
      // oficiales): esperarlo con `await` antes de arrancar el bucle dejaba
      // la pantalla en negro en los móviles donde esa promesa tarda.
      if (!fuentePedida) {
        fuentePedida = true
        sesion.requestReferenceSpace('viewer').then((visor) => {
          sesion.requestHitTestSource!({ space: visor })!.then((f) => {
            fuenteHitTest = f ?? null
          })
        })
      }

      let hay = false
      if (fuenteHitTest) {
        const res = frame.getHitTestResults(fuenteHitTest)
        if (res.length > 0) {
          const pose = res[0].getPose(referencia)
          if (pose) {
            hay = true
            reticulo.visible = true
            reticulo.matrix.fromArray(pose.transform.matrix)
            ultimaPoseRef.current = new THREE.Vector3().setFromMatrixPosition(reticulo.matrix)
          }
        }
      }
      if (!hay) reticulo.visible = false

      // La interfaz de React se refresca con cuentagotas (~6 fps): en cada
      // frame saturaría el render sin que se note la diferencia.
      if (frames++ % 10 === 0) {
        setSuperficie(hay)
        const p = ultimaPoseRef.current
        setPosicionActual(hay && p && !cerradoRef.current ? { x: p.x, z: p.z } : null)
      }
      renderer.render(scene, camara3d)
    })
  }

  function deshacer() {
    if (cerradoRef.current) {
      cerradoRef.current = false
      setRevision(null)
    } else {
      puntosRef.current = puntosRef.current.slice(0, -1)
      // La foto de esa esquina se va con ella, para que la lista de fotos
      // siga cuadrando con la de vértices.
      fotosRef.current = fotosRef.current.slice(0, -1)
      setNFotos(fotosRef.current.length)
    }
    redibujarEscenaRef.current?.()
    sincronizarPlanta()
  }

  /** Longitud de cada muro del perímetro cerrado, en metros — tal cual las
   *  midió el AR. Es lo que viaja a la IA para que sepa a qué muro asignar
   *  cada elemento; no se le pide que las recalcule. */
  function murosDe(vertices: THREE.Vector3[]): number[] {
    return vertices.map((a, i) => {
      const b = vertices[(i + 1) % vertices.length]
      return Math.hypot(b.x - a.x, b.z - a.z)
    })
  }

  async function cerrarPerimetro() {
    if (puntosRef.current.length < 3) return
    cerradoRef.current = true
    redibujarEscenaRef.current?.()
    sincronizarPlanta()

    const fotos = fotosRef.current
    if (fotos.length === 0) return // sin `camera-access` no hay nada que revisar
    setRevisando(true)
    setError(null)
    try {
      setRevision(
        await apiPublico.testmeter.revisarPlanta(fotos, murosDe(puntosRef.current), proveedor),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setRevisando(false)
    }
  }

  function empezarDeCero() {
    puntosRef.current = []
    cerradoRef.current = false
    fotosRef.current = []
    setNFotos(0)
    setRevision(null)
    redibujarEscenaRef.current?.()
    sincronizarPlanta()
  }

  function salir() {
    sesionRef.current?.end()
  }

  useEffect(() => {
    return () => {
      sesionRef.current?.end()
    }
  }, [])

  const area = cerrado ? areaDe(puntos) : 0
  const perimetro = perimetroDe(puntos, cerrado)
  const ultimoTramo =
    puntos.length >= 2
      ? Math.hypot(
          puntos[puntos.length - 1].x - puntos[puntos.length - 2].x,
          puntos[puntos.length - 1].z - puntos[puntos.length - 2].z,
        )
      : null

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--c-bg)',
        color: 'var(--c-text)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: 'var(--sp-4)',
        gap: 'var(--sp-4)',
      }}
    >
      <img src={logo} alt="Flexómetro" style={{ height: 32, width: 'auto' }} />
      <p className="muted" style={{ margin: 0, textAlign: 'center', maxWidth: 520 }}>
        Levanta la planta caminando: marca cada esquina con el retículo y cierra el perímetro. El AR
        pone las coordenadas reales; la IA reconoce qué hay en el espacio. Solo{' '}
        <strong>Chrome/Android con ARCore</strong>.
      </p>

      <ErrorNotice error={error} />

      {soportado === false && (
        <p className="notice notice--error" style={{ maxWidth: 520, textAlign: 'center' }}>
          Este dispositivo o navegador no soporta AR (WebXR). Pruébalo en Chrome sobre un Android con
          ARCore.
        </p>
      )}

      {/* ── Antes de entrar en AR: previsualización + reconocimiento IA ── */}
      {etapa !== 'levantando' && (
        <>
          <div style={{ width: '100%', maxWidth: 520 }}>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{ width: '100%', borderRadius: 12, background: '#000' }}
            />
          </div>

          {reconocido && (
            <div style={{ width: '100%', maxWidth: 520 }}>
              {reconocido.elementos.length > 0 && (
                <p className="notice" style={{ margin: 0 }}>
                  <strong>La IA reconoce:</strong>{' '}
                  {reconocido.elementos.map((e) => e.label).join(', ')}.
                  {reconocido.razonamiento && (
                    <>
                      <br />
                      {reconocido.razonamiento}
                    </>
                  )}
                </p>
              )}
              {reconocido.metricas && (
                <p
                  className="muted"
                  style={{ margin: 'var(--sp-2) 0 0', fontSize: '0.85em', textAlign: 'center' }}
                >
                  <strong>{reconocido.metricas.modelo}</strong> ·{' '}
                  {(reconocido.metricas.ms / 1000).toFixed(1)} s ·{' '}
                  {reconocido.metricas.tokens_entrada + reconocido.metricas.tokens_salida} tokens (
                  {reconocido.metricas.tokens_entrada} entrada /{' '}
                  {reconocido.metricas.tokens_salida} salida
                  {reconocido.metricas.tokens_razonamiento > 0 &&
                    `, de ellos ${reconocido.metricas.tokens_razonamiento} razonando`}
                  ) · {reconocido.elementos.length} elementos
                </p>
              )}
            </div>
          )}

          <div style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
            <span className="muted" style={{ fontSize: '0.85em' }}>
              Motor de visión:
            </span>
            {(['gemini', 'deepseek'] as ProveedorVision[]).map((p) => (
              <button
                key={p}
                type="button"
                className={`btn btn--sm${proveedor === p ? ' btn--primary' : ''}`}
                onClick={() => setProveedor(p)}
                disabled={etapa === 'reconociendo'}
              >
                {p === 'gemini' ? 'Gemini' : 'DeepSeek'}
              </button>
            ))}
          </div>

          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', justifyContent: 'center' }}>
            <button
              type="button"
              className="btn"
              onClick={reconocerEspacio}
              disabled={etapa === 'reconociendo'}
            >
              {etapa === 'reconociendo' ? (
                <>
                  <Loader2 size={16} className="girando" aria-hidden="true" /> Reconociendo…
                </>
              ) : (
                <>
                  <Camera size={16} aria-hidden="true" /> Reconocer el espacio
                </>
              )}
            </button>
            {soportado && (
              <button type="button" className="btn btn--primary" onClick={iniciarLevantamiento}>
                <MapPin size={16} aria-hidden="true" /> Levantar planta
              </button>
            )}
          </div>
        </>
      )}

      {/* WebXR pinta la cámara y el <canvas> de Three.js aquí dentro. */}
      <div ref={contenedorRef} />

      {/* ── Pantalla partida durante el levantamiento: 60% cámara, 40% planta ── */}
      <div ref={overlayRef} style={{ position: etapa === 'levantando' ? 'fixed' : 'static', inset: 0 }}>
        {etapa === 'levantando' && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              flexDirection: 'column',
              pointerEvents: 'none',
            }}
          >
            {/* 60% — cámara. Sin pointerEvents para que el toque llegue al AR
                y dispare 'select' (marcar esquina). */}
            <div
              style={{
                height: '60%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div
                style={{
                  padding: 'var(--sp-3)',
                  background: 'linear-gradient(rgba(0,0,0,0.75), transparent)',
                  color: '#fff',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontWeight: 700 }}>
                  {cerrado
                    ? revisando
                      ? 'Revisando las fotos con la IA…'
                      : revision
                        ? `Planta lista · ${revision.elementos.length} elemento(s) detectado(s)`
                        : 'Perímetro cerrado'
                    : puntos.length === 0
                      ? 'Apunta a la primera esquina y toca'
                      : `Esquina ${puntos.length} marcada — ve a la siguiente`}
                </div>
                <div style={{ fontSize: '0.85rem', color: superficie ? '#86efac' : '#fcd34d' }}>
                  {superficie ? '● Superficie detectada' : '○ Buscando superficie… mueve el móvil'}
                </div>
                {ultimoTramo !== null && !cerrado && (
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, marginTop: 2 }}>
                    Último tramo: {formatoCota(ultimoTramo)}
                  </div>
                )}
                {error && <div style={{ color: '#fca5a5', fontSize: '0.8rem' }}>{error}</div>}
              </div>

              <div style={{ padding: 'var(--sp-3)', display: 'flex', justifyContent: 'center' }}>
                <button
                  type="button"
                  onClick={() => marcarRef.current?.()}
                  disabled={!superficie || cerrado}
                  style={{
                    pointerEvents: 'auto',
                    width: 66,
                    height: 66,
                    borderRadius: '50%',
                    border: '4px solid #fff',
                    background: superficie && !cerrado ? NARANJA_CSS : 'rgba(255,255,255,0.25)',
                    color: '#fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                  aria-label="Marcar esquina"
                >
                  <MapPin size={26} aria-hidden="true" />
                </button>
              </div>
            </div>

            {/* 40% — planta en vivo, siempre autoencuadrada. */}
            <div
              style={{
                height: '40%',
                background: 'rgba(12,14,18,0.94)',
                borderTop: '1px solid rgba(255,255,255,0.15)',
                display: 'flex',
                flexDirection: 'column',
                pointerEvents: 'auto',
              }}
            >
              <div
                style={{
                  padding: '6px var(--sp-3)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  color: '#fff',
                  fontSize: '0.82rem',
                }}
              >
                <span style={{ opacity: 0.75 }}>
                  {puntos.length} {puntos.length === 1 ? 'esquina' : 'esquinas'}
                  {nFotos > 0 && ` · ${nFotos} 📷`}
                  {perimetro > 0 && ` · ${formatoCota(perimetro)}`}
                </span>
                {revisando ? (
                  <span style={{ color: '#fde68a', display: 'inline-flex', gap: 4 }}>
                    <Loader2 size={13} className="girando" aria-hidden="true" /> Revisando con IA…
                  </span>
                ) : (
                  cerrado && area > 0 && <strong style={{ color: '#fde68a' }}>{area.toFixed(2)} m²</strong>
                )}
              </div>

              <div style={{ flex: 1, minHeight: 0 }}>
                <PlantaLevantamiento
                  puntos={puntos}
                  cerrado={cerrado}
                  posicionActual={posicionActual}
                  elementos={revision?.elementos ?? []}
                />
              </div>

              <div
                style={{
                  padding: 'var(--sp-2) var(--sp-3)',
                  display: 'flex',
                  gap: 'var(--sp-2)',
                  justifyContent: 'center',
                  flexWrap: 'wrap',
                }}
              >
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={deshacer}
                  disabled={puntos.length === 0 && !cerrado}
                  style={BOTON_SOBRE_OSCURO}
                >
                  <Undo2 size={14} aria-hidden="true" /> Deshacer
                </button>
                <button
                  type="button"
                  className="btn btn--sm btn--primary"
                  onClick={cerrarPerimetro}
                  disabled={puntos.length < 3 || cerrado}
                >
                  <Check size={14} aria-hidden="true" /> Cerrar
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={empezarDeCero}
                  disabled={puntos.length === 0}
                  style={BOTON_SOBRE_OSCURO}
                >
                  <RotateCcw size={14} aria-hidden="true" /> Vaciar
                </button>
                <button type="button" className="btn btn--sm" onClick={salir} style={BOTON_SOBRE_OSCURO}>
                  <X size={14} aria-hidden="true" /> Salir
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
