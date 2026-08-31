import { useCallback, useEffect, useRef, useState } from 'react'
import { Copy, Download, Plus, Send } from 'lucide-react'

import { EditorFirmantes } from '../components/EditorFirmantes'
import type { EditorFirmantesHandle } from '../components/EditorFirmantes'
import { BibliotecaPdf, ZonaSoltarPdf } from '../components/SelectorPdf'
import { VisorFirmas } from '../components/VisorFirmas'
import { FichaDetalle } from '../components/FichaDetalle'
import type { PestanaFicha } from '../components/FichaDetalle'
import { EmptyState, ErrorNotice, Field, IconButton, Modal, Pager } from '../components/ui'
import { api, descargar } from '../lib/api'
import { useToast } from '../toast'
import type {
  DatosSolicitudFirma,
  Documento,
  DocumentoBusqueda,
  EnvioFirma,
  PosicionFirma,
  EstadoFirma,
  EstadoFirmante,
  CanalEnvio,
  PlantillaDocumento,
  PreferenciaCanal,
  SolicitudFirma,
  SolicitudFirmaDetalle,
} from '../lib/api'

const ETIQUETA_ESTADO: Record<EstadoFirma, string> = {
  borrador: 'Borrador',
  enviada: 'Enviada',
  vista: 'Abierta',
  parcial: 'Firmas parciales',
  firmada: 'Firmada',
  rechazada: 'Rechazada',
  cancelada: 'Cancelada',
}

const ETIQUETA_FIRMANTE: Record<EstadoFirmante, string> = {
  pendiente: 'Pendiente',
  vista: 'Ha abierto',
  firmada: 'Firmada',
  rechazada: 'Rechazada',
}

const CLASE_ESTADO_FIRMANTE: Record<EstadoFirmante, string> = {
  pendiente: '',
  vista: 'notice--aviso',
  firmada: 'notice--ok',
  rechazada: 'notice--error',
}

const CLASE_ESTADO: Record<EstadoFirma, string> = {
  borrador: '',
  enviada: 'notice--aviso',
  vista: 'notice--aviso',
  parcial: 'notice--aviso',
  firmada: 'notice--ok',
  rechazada: 'notice--error',
  cancelada: '',
}

/** «WhatsApp», «correo» o «WhatsApp y correo». */
function nombreCanales(canales: CanalEnvio[] | null | undefined): string {
  const nombres = (canales ?? []).map((c) => (c === 'whatsapp' ? 'WhatsApp' : 'correo'))
  return nombres.length > 1 ? `${nombres.slice(0, -1).join(', ')} y ${nombres.at(-1)}` : nombres[0] ?? ''
}

/** Documentos mandados a firmar a terceros y su estado. */
export function Firmas() {
  const { notificar } = useToast()
  const [solicitudes, setSolicitudes] = useState<SolicitudFirma[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [modal, setModal] = useState(false)
  const [detalle, setDetalle] = useState<SolicitudFirmaDetalle | null>(null)
  const [envios, setEnvios] = useState<EnvioFirma[]>([])
  const [avisoEnvio, setAvisoEnvio] = useState<string | null>(null)
  const limite = 25

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const pagina = await api.prl.firmas.list({ limit: limite, offset })
      setSolicitudes(pagina.items)
      setTotal(pagina.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [offset])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function enviar(id: string) {
    setError(null)
    setAvisoEnvio(null)
    try {
      const resultados = await api.prl.firmas.enviar(id)
      setEnvios(resultados)
      // Los enlaces son válidos aunque el correo falle: se enseñan siempre
      // para poder mandarlos a mano, y solo se avisa de los que no salieron.
      const fallidos = resultados.filter((r) => !r.enviado)
      if (fallidos.length > 0) {
        setAvisoEnvio(
          `No se ha podido enviar el correo a ${fallidos.length} de ${resultados.length} ` +
            'firmante(s). Copia su enlace y mándaselo tú.',
        )
      }
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  /** Manda el enlace a UNO solo: el que se acaba de añadir, o el que dice que
   *  no le llegó. */
  async function reenviarA(firmanteId: string) {
    setError(null)
    setAvisoEnvio(null)
    try {
      const [resultado] = await api.prl.firmas.enviar(detalle!.id, firmanteId)
      if (resultado?.enviado) {
        notificar(
          `Enviado a ${resultado.firmante_nombre}` +
            (resultado.canales.length ? ` por ${nombreCanales(resultado.canales)}` : ''),
        )
      } else {
        setAvisoEnvio(
          `No se ha podido avisar a ${resultado?.firmante_nombre ?? 'ese firmante'}. ` +
            'Copia su enlace y mándaselo tú.',
        )
      }
      if (resultado?.enlace) setEnvios([resultado])
      setDetalle(await api.prl.firmas.get(detalle!.id))
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function quitarFirmante(firmanteId: string, nombre: string) {
    if (!window.confirm(`¿Quitar a ${nombre} de este documento? Su enlace dejará de valer.`))
      return
    setError(null)
    try {
      setDetalle(await api.prl.firmas.quitarFirmante(detalle!.id, firmanteId))
      notificar(`${nombre} ya no tiene que firmar`)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Documentos a firmar</h1>
        <IconButton icono="nuevo" texto="Nuevo documento" variante="primary" onClick={() => setModal(true)} />
      </div>

      <ErrorNotice error={error} />
      {avisoEnvio && <p className="notice notice--aviso">{avisoEnvio}</p>}
      {envios.length > 0 && (
        <div className={`notice ${envios.every((e) => e.enviado) ? 'notice--ok' : 'notice--aviso'}`}>
          <strong>Enlaces de firma</strong>
          {envios.map((envio) => (
            <p key={envio.enlace || envio.firmante_nombre} style={{ margin: '6px 0', wordBreak: 'break-all' }}>
              {envio.enviado ? '✓' : '✕'} <strong>{envio.firmante_nombre}</strong>
              {envio.enlace && (
                <>
                  : {envio.enlace}{' '}
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => navigator.clipboard?.writeText(envio.enlace)}
                  >
                    <Copy size={14} aria-hidden="true" /> Copiar
                  </button>
                </>
              )}
              {envio.error && (
                <span className="muted" style={{ fontSize: '0.85em' }}> — {envio.error}</span>
              )}
            </p>
          ))}
        </div>
      )}

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : solicitudes.length === 0 ? (
        <EmptyState title="Sin documentos a firmar">
          Manda un acta de coordinación, un acuse de entrega o cualquier documento a un proveedor
          para que lo firme desde un enlace, sin necesidad de que tenga cuenta.
        </EmptyState>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Documento</th>
                <th>Firmantes</th>
                <th>Estado</th>
                <th>Progreso</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {solicitudes.map((solicitud) => (
                <tr key={solicitud.id}>
                  <td>{solicitud.codigo}</td>
                  <td>{solicitud.titulo}</td>
                  <td>
                    {solicitud.firmantes.map((firmante) => (
                      <div key={firmante.id} style={{ fontSize: '0.9em' }}>
                        {firmante.estado === 'firmada' ? '✓' : firmante.estado === 'rechazada' ? '✕' : '·'}{' '}
                        {firmante.nombre}
                      </div>
                    ))}
                  </td>
                  <td>
                    <span
                      className={`notice ${CLASE_ESTADO[solicitud.estado]}`}
                      style={{ margin: 0, padding: '2px 8px', display: 'inline-block' }}
                    >
                      {ETIQUETA_ESTADO[solicitud.estado]}
                    </span>
                  </td>
                  <td>
                    <strong>
                      {solicitud.firmas_hechas} / {solicitud.total_firmantes}
                    </strong>
                    <div className="muted" style={{ fontSize: '0.85em' }}>
                      firmas
                    </div>
                  </td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {solicitud.documento_id && (
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() =>
                          void descargar(
                            api.documentos.descargarUrl(solicitud.documento_id!),
                            `${solicitud.codigo}-firmado.pdf`,
                            { abrir: true },
                          )
                        }
                      >
                        <Download size={14} aria-hidden="true" /> PDF
                      </button>
                    )}{' '}
                    {solicitud.estado !== 'firmada' && solicitud.estado !== 'cancelada' && (
                      <button
                        type="button"
                        className="btn btn--sm btn--primary"
                        onClick={() => enviar(solicitud.id)}
                      >
                        <Send size={14} aria-hidden="true" />{' '}
                        {solicitud.estado === 'borrador' ? 'Enviar' : 'Reenviar'}
                      </button>
                    )}{' '}
                    <button
                      type="button"
                      className="btn btn--sm"
                      onClick={async () => setDetalle(await api.prl.firmas.get(solicitud.id))}
                    >
                      Ver
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pager total={total} limit={limite} offset={offset} onChange={setOffset} />

      {modal && (
        <NuevaSolicitud
          onCerrar={() => setModal(false)}
          onCreada={async () => {
            setModal(false)
            await cargar()
          }}
        />
      )}

      {detalle && (
        <Modal title={`${detalle.codigo} · ${detalle.titulo}`} onClose={() => setDetalle(null)}>
          <div className="form-section">
            <div
              className="contenido-documento"
              style={{ border: '1px solid var(--c-border)', borderRadius: 8, padding: 'var(--sp-4)' }}
              // El contenido ya viene saneado del servidor (`sanear_html` al
              // crear la solicitud), que es donde tiene que estar el filtro.
              dangerouslySetInnerHTML={{ __html: detalle.contenido_html }}
            />
            <GestionFirmantes
              detalle={detalle}
              onCambio={async (actualizado) => {
                setDetalle(actualizado)
                // La lista de fuera enseña «firmas hechas / total»: si no se
                // recarga, se queda contando mal.
                await cargar()
              }}
            />

            {detalle.firmantes.map((firmante) => (
            <div
              key={firmante.id}
              style={{
                marginTop: 'var(--sp-3)',
                paddingTop: 'var(--sp-3)',
                borderTop: '1px solid var(--c-border)',
              }}
            >
              <div style={{ fontWeight: 600 }}>
                {firmante.nombre}{' '}
                <span
                  className={`notice ${CLASE_ESTADO_FIRMANTE[firmante.estado]}`}
                  style={{ margin: 0, padding: '1px 7px', fontSize: '0.8em' }}
                >
                  {ETIQUETA_FIRMANTE[firmante.estado]}
                </span>
              </div>
              {firmante.firma_imagen && (
                <img
                  src={firmante.firma_imagen}
                  alt={`Firma de ${firmante.nombre}`}
                  style={{ maxHeight: 70, background: '#fff', borderRadius: 6, marginTop: 4 }}
                />
              )}
              <p className="muted" style={{ fontSize: '0.85em', margin: '4px 0 0' }}>
                {firmante.email}
                {firmante.telefono && ` · ${firmante.telefono}`}
                {/* Por dónde se le mandó el enlace: es parte de la evidencia,
                    no un detalle de interfaz. */}
                {firmante.canales_envio?.length
                  ? ` · enviado por ${nombreCanales(firmante.canales_envio)}`
                  : ''}
                {firmante.firmante_nombre && ` · firmó como ${firmante.firmante_nombre}`}
                {firmante.firmante_dni && ` (${firmante.firmante_dni})`}
                {firmante.firmada_en && ` · ${new Date(firmante.firmada_en).toLocaleString()}`}
                {firmante.ip_firma && ` · IP ${firmante.ip_firma}`}
              </p>
              {firmante.motivo_rechazo && (
                <p className="notice notice--error" style={{ marginTop: 4 }}>
                  <strong>Rechazado:</strong> {firmante.motivo_rechazo}
                </p>
              )}
              {/* Solo mientras esa persona no haya respondido: una firma o un
                  rechazo son evidencia y no se tocan. */}
              {(firmante.estado === 'pendiente' || firmante.estado === 'vista') && (
                <div style={{ display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)' }}>
                  <button
                    className="btn btn--sm"
                    onClick={() => void reenviarA(firmante.id)}
                  >
                    <Send size={13} aria-hidden="true" />{' '}
                    {firmante.enviada_en ? 'Reenviar' : 'Enviar'}
                  </button>
                  <button
                    className="btn btn--sm btn--danger"
                    onClick={() => void quitarFirmante(firmante.id, firmante.nombre)}
                  >
                    Quitar
                  </button>
                </div>
              )}
            </div>
          ))}
          {detalle.hash_documento && (
            <p className="muted" style={{ fontSize: '0.78em', marginTop: 'var(--sp-3)', wordBreak: 'break-all' }}>
              Huella SHA-256 del documento firmado: {detalle.hash_documento}
            </p>
          )}
          </div>
        </Modal>
      )}
    </div>
  )
}

/** Estado de la firma y alta de un firmante que se quedó fuera.
 *
 *  Existe porque olvidarse de alguien al crear la solicitud es lo normal, y
 *  hasta ahora obligaba a tirar el documento y rehacerlo entero — con lo que
 *  quien ya había firmado tenía que volver a hacerlo. */
function GestionFirmantes({
  detalle,
  onCambio,
}: {
  detalle: SolicitudFirmaDetalle
  onCambio: (detalle: SolicitudFirmaDetalle) => void | Promise<void>
}) {
  const [abierto, setAbierto] = useState(false)
  const [nombre, setNombre] = useState('')
  const [email, setEmail] = useState('')
  const [telefono, setTelefono] = useState('')
  const [guardando, setGuardando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Con el documento cerrado ya existe un PDF sellado con unas firmas
  // concretas; meter a alguien después lo dejaría mintiendo.
  const cerrado =
    detalle.estado === 'firmada' ||
    detalle.estado === 'rechazada' ||
    detalle.estado === 'cancelada'

  async function anadir() {
    if (!nombre.trim() || !email.trim()) {
      setError('Hacen falta el nombre y el correo.')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      const actualizado = await api.prl.firmas.anadirFirmante(detalle.id, {
        nombre: nombre.trim(),
        email: email.trim(),
        telefono: telefono.trim() || null,
      })
      setNombre('')
      setEmail('')
      setTelefono('')
      setAbierto(false)
      await onCambio(actualizado)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 'var(--sp-3)',
        flexWrap: 'wrap',
        marginTop: 'var(--sp-4)',
      }}
    >
      <div>
        <strong>
          {detalle.firmas_hechas} de {detalle.total_firmantes} firmas
        </strong>
        {!cerrado && detalle.total_firmantes > detalle.firmas_hechas && (
          <span className="muted" style={{ marginLeft: 'var(--sp-2)', fontSize: '0.9em' }}>
            Falta{detalle.total_firmantes - detalle.firmas_hechas > 1 ? 'n' : ''}{' '}
            {detalle.total_firmantes - detalle.firmas_hechas}
          </span>
        )}
      </div>
      {!cerrado && !abierto && (
        <button className="btn btn--sm" onClick={() => setAbierto(true)}>
          <Plus size={14} aria-hidden="true" /> Añadir firmante
        </button>
      )}

      {abierto && (
        <div style={{ width: '100%' }}>
          <ErrorNotice error={error} />
          <div className="form-grid">
            <Field label="Nombre">
              <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
            </Field>
            <Field label="Correo">
              <input
                className="input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="Móvil (opcional)" hint="Con móvil, el enlace le llega por WhatsApp">
              <input
                className="input"
                type="tel"
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
              />
            </Field>
          </div>
          <div className="form-actions">
            <button className="btn" onClick={() => setAbierto(false)} disabled={guardando}>
              Cancelar
            </button>
            <button className="btn btn--primary" onClick={() => void anadir()} disabled={guardando}>
              {guardando ? 'Añadiendo…' : 'Añadir'}
            </button>
          </div>
          <p className="muted" style={{ fontSize: '0.85em', margin: 0 }}>
            Se añade sin avisarle: su enlace sale cuando le des a <strong>Enviar</strong> en su
            ficha, justo debajo.
          </p>
        </div>
      )}
    </div>
  )
}

type Origen = 'plantilla' | 'escribir' | 'subir' | 'biblioteca'

const CANALES: [PreferenciaCanal, string][] = [
  ['auto', 'Automático (recomendado)'],
  ['whatsapp', 'Solo WhatsApp'],
  ['email', 'Solo correo'],
  ['ambos', 'WhatsApp y correo'],
]

const ORIGENES: [Origen, string][] = [
  ['plantilla', 'Desde una plantilla'],
  ['escribir', 'Escribir el texto'],
  ['subir', 'Subir un PDF'],
  ['biblioteca', 'De la biblioteca'],
]

function NuevaSolicitud({
  onCerrar,
  onCreada,
}: {
  onCerrar: () => void
  onCreada: () => void
}) {
  const [origen, setOrigen] = useState<Origen>('plantilla')
  const [plantillas, setPlantillas] = useState<PlantillaDocumento[]>([])
  const editorRef = useRef<EditorFirmantesHandle>(null)
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [datos, setDatos] = useState<DatosSolicitudFirma>({
    titulo: '',
    firmantes: [],
    plantilla_id: null,
    contenido_html: '',
    dias_validez: 30,
    canal_enlace: 'auto',
    canal_codigo: 'auto',
  })
  // Las posiciones se llevan por firmante, indexadas por CORREO y no por su
  // posición en la lista. Con índices, quitar a alguien de en medio corría
  // los recuadros de los demás y cada uno acababa firmando donde no era: el
  // correo identifica a la persona y no se mueve. `firmanteActivo` es el
  // correo de aquel sobre el que trabaja el visor.
  const [firmanteActivo, setFirmanteActivo] = useState<string | null>(null)
  const [posicionesPorFirmante, setPosicionesPorFirmante] = useState<
    Record<string, PosicionFirma[]>
  >({})

  /** Misma clave para todos: el correo, en minúsculas. */
  const clave = (firmante: { email: string }) => firmante.email.trim().toLowerCase()
  const [pdf, setPdf] = useState<File | null>(null)
  // Documento elegido de la biblioteca: se guarda entero (no solo el id) para
  // poder enseñar cuál es sin volver a pedirlo.
  const [deBiblioteca, setDeBiblioteca] = useState<Documento | DocumentoBusqueda | null>(null)

  useEffect(() => {
    api.prl.plantillas.list({ solo_activas: true }).then(setPlantillas).catch(() => setPlantillas([]))
  }, [])

  function cambiarOrigen(nuevo: Origen) {
    setOrigen(nuevo)
    // Limpia lo del origen anterior: si no, se podría mandar una plantilla Y
    // un PDF a la vez y el servidor tendría que decidir por su cuenta.
    setDatos((previo) => ({ ...previo, plantilla_id: null, contenido_html: '' }))
    setDeBiblioteca(null)
    setPdf(null)
    setPosicionesPorFirmante({})
  }

  // URL del PDF para el visor. Con un fichero aún sin subir se usa un
  // `blob:` local; con uno de la biblioteca, su descarga autenticada. Se
  // revoca al cambiar para no dejar blobs colgando en memoria.
  const [urlVista, setUrlVista] = useState<string | null>(null)
  useEffect(() => {
    let vigente: string | null = null
    if (origen === 'subir' && pdf) {
      vigente = URL.createObjectURL(pdf)
      setUrlVista(vigente)
    } else if (origen === 'biblioteca' && deBiblioteca) {
      setUrlVista(api.documentos.descargarUrl(deBiblioteca.id))
    } else {
      setUrlVista(null)
    }
    return () => {
      if (vigente) URL.revokeObjectURL(vigente)
    }
  }, [origen, pdf, deBiblioteca])

  async function crear() {
    if (!datos.titulo.trim()) {
      setError('Hace falta el título del documento.')
      return
    }
    // Lo tecleado en el editor y no añadido se recoge ahora. Antes se perdía
    // en silencio y el documento salía con un firmante menos.
    //
    // Se usa la lista que DEVUELVE el editor, no `datos.firmantes`: recoger
    // lo pendiente dispara un `setState` del padre, que en este mismo render
    // todavía no ha llegado — leerlo de `datos` volvería a mandar sin él.
    // Ojo con `??` aquí: se tragaría también el `null` de «hay algo a medias»
    // y la comprobación de debajo no llegaría a saltar nunca.
    const editor = editorRef.current
    const firmantes = editor ? editor.confirmarPendiente() : datos.firmantes
    if (firmantes === null) {
      setError('Completa o borra el firmante que tienes a medio escribir.')
      return
    }
    if (firmantes.length === 0) {
      setError('Añade al menos un firmante.')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      let documentoOrigenId: string | null = null

      if (origen === 'subir') {
        if (!pdf) throw new Error('Arrastra o elige el PDF que hay que firmar.')
        // Se sube a la biblioteca como cualquier otro documento: así queda
        // trazado y se puede reutilizar, en vez de vivir suelto en la firma.
        const subido = await api.documentos.upload('solicitud_firma', crypto.randomUUID(), pdf)
        documentoOrigenId = subido.id
      } else if (origen === 'biblioteca') {
        if (!deBiblioteca) throw new Error('Elige un documento de la biblioteca.')
        documentoOrigenId = deBiblioteca.id
      } else if (origen === 'plantilla') {
        if (!datos.plantilla_id) throw new Error('Elige una plantilla.')
      } else if (!datos.contenido_html?.trim()) {
        throw new Error('Escribe el contenido del documento.')
      }

      const solicitud = await api.prl.firmas.create({
        ...datos,
        firmantes,
        documento_origen_id: documentoOrigenId,
      })
      // Las posiciones van en una llamada aparte: solo existen cuando el
      // origen es un PDF, y necesitan los ids de firmante que el servidor
      // acaba de crear.
      // Se emparejan por correo con los que acaba de crear el servidor, no
      // por el orden en que vuelven: depender del orden es apostar a que dos
      // listas coincidan siempre, y basta un cambio en el servidor para que
      // cada firma acabe en el recuadro de otro.
      const conPosiciones = solicitud.firmantes
        .map((firmante) => ({
          firmante_id: firmante.id,
          posiciones: posicionesPorFirmante[clave(firmante)] ?? [],
        }))
        .filter((entrada) => entrada.posiciones.length > 0)
      if (conPosiciones.length > 0) {
        await api.prl.firmas.posiciones(solicitud.id, conPosiciones)
      }
      onCreada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  /** Si el enlace y su código acaban en el mismo sitio, quien tenga acceso a
   *  ese canal tiene las dos mitades: el segundo factor deja de serlo. No se
   *  impide —puede haber motivos— pero se dice. */
  const avisoCanales = (() => {
    const enlace = datos.canal_enlace ?? 'auto'
    const codigo = datos.canal_codigo ?? 'auto'
    if (enlace === 'auto' || codigo === 'auto') return null
    const comparten =
      enlace === codigo || enlace === 'ambos' || codigo === 'ambos'
    return comparten
      ? 'El enlace y su código llegarán por el mismo sitio: quien acceda a ese canal ' +
          'tendrá las dos mitades y la verificación en dos pasos dejará de aportar nada.'
      : null
  })()

  /** La barra de acciones va al final de cada pestaña, como en el resto de
   *  fichas: se puede crear el borrador desde cualquiera de ellas sin tener
   *  que volver a la primera. */
  const acciones = (
    <div className="form-actions">
      <button type="button" className="btn" onClick={onCerrar}>
        Cancelar
      </button>
      <button type="button" className="btn btn--primary" onClick={crear} disabled={guardando}>
        {guardando ? 'Creando…' : 'Crear borrador'}
      </button>
    </div>
  )

  const pestanas: PestanaFicha[] = [
    {
      id: 'documento',
      etiqueta: 'Documento',
      icono: 'file-text',
      contenido: (
        <div className="form-section">
          <ErrorNotice error={error} />

          <Field ancho="completo" label="¿De dónde sale el documento?">
            <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
              {ORIGENES.map(([valor, etiqueta]) => (
                <button
                  key={valor}
                  type="button"
                  className={`btn btn--sm${origen === valor ? ' btn--primary' : ''}`}
                  onClick={() => cambiarOrigen(valor)}
                >
                  {etiqueta}
                </button>
              ))}
            </div>
          </Field>

          <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
            <Field ancho="doble" label="Título del documento">
              <input
                className="input"
                value={datos.titulo}
                onChange={(e) => setDatos((previo) => ({ ...previo, titulo: e.target.value }))}
              />
            </Field>
            <Field label="Validez del enlace (días)">
              <input
                className="input"
                type="number"
                min={1}
                max={365}
                value={datos.dias_validez ?? 30}
                onChange={(e) =>
                  setDatos((previo) => ({ ...previo, dias_validez: Number(e.target.value) }))
                }
              />
            </Field>

            {origen === 'plantilla' && (
              <Field ancho="doble" label="Plantilla">
                <select
                  className="input"
                  value={datos.plantilla_id ?? ''}
                  onChange={(e) => {
                    const elegida = plantillas.find((p) => p.id === e.target.value)
                    setDatos((previo) => ({
                      ...previo,
                      plantilla_id: e.target.value || null,
                      titulo: previo.titulo || elegida?.nombre || '',
                    }))
                  }}
                >
                  <option value="">Selecciona una plantilla…</option>
                  {plantillas.map((plantilla) => (
                    <option key={plantilla.id} value={plantilla.id}>
                      {plantilla.nombre}
                    </option>
                  ))}
                </select>
              </Field>
            )}

            {origen === 'escribir' && (
              <Field ancho="completo" label="Contenido del documento">
                <textarea
                  className="input"
                  rows={14}
                  value={datos.contenido_html ?? ''}
                  onChange={(e) =>
                    setDatos((previo) => ({ ...previo, contenido_html: e.target.value }))
                  }
                />
              </Field>
            )}

            {origen === 'subir' && (
              <Field
                ancho="completo"
                label="PDF a firmar"
                hint="Se guarda también en la biblioteca, para que quede trazado"
              >
                <ZonaSoltarPdf fichero={pdf} onFichero={setPdf} />
              </Field>
            )}

            {origen === 'biblioteca' && (
              <Field ancho="completo" label="Biblioteca de documentos" hint="Solo se listan PDF">
                <BibliotecaPdf elegido={deBiblioteca} onElegir={setDeBiblioteca} />
              </Field>
            )}
          </div>
          {acciones}
        </div>
      ),
    },
    {
      id: 'firmantes',
      etiqueta: `Firmantes${datos.firmantes.length ? ` (${datos.firmantes.length})` : ''}`,
      icono: 'users',
      contenido: (
        <div className="form-section">
          <ErrorNotice error={error} />
          <div className="form-grid" style={{ marginBottom: 'var(--sp-4)' }}>
            <Field
              label="Mandar el enlace por"
              hint="En automático: WhatsApp si tiene móvil; si no, correo"
            >
              <select
                className="select"
                value={datos.canal_enlace ?? 'auto'}
                onChange={(e) =>
                  setDatos((previo) => ({
                    ...previo,
                    canal_enlace: e.target.value as PreferenciaCanal,
                  }))
                }
              >
                {CANALES.map(([valor, etiqueta]) => (
                  <option key={valor} value={valor}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field
              label="Mandar el código por"
              hint="En automático: por donde NO haya ido el enlace"
            >
              <select
                className="select"
                value={datos.canal_codigo ?? 'auto'}
                onChange={(e) =>
                  setDatos((previo) => ({
                    ...previo,
                    canal_codigo: e.target.value as PreferenciaCanal,
                  }))
                }
              >
                {CANALES.map(([valor, etiqueta]) => (
                  <option key={valor} value={valor}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            {avisoCanales && (
              <div className="field field--completo">
                <p className="notice">{avisoCanales}</p>
              </div>
            )}
          </div>

          <EditorFirmantes
            ref={editorRef}
            firmantes={datos.firmantes}
            terceroId={datos.tercero_id}
            onCambio={(firmantes) => {
              // Funcional: si no, se pisaría cualquier otro cambio de
              // `datos` hecho en este mismo render.
              setDatos((previo) => ({ ...previo, firmantes }))
              // Se tiran las posiciones de quien ya no está; las de los
              // demás no se tocan, porque van por correo.
              setPosicionesPorFirmante((previo) =>
                Object.fromEntries(firmantes.map((f) => [clave(f), previo[clave(f)] ?? []])),
              )
              setFirmanteActivo((previo) =>
                previo && firmantes.some((f) => clave(f) === previo)
                  ? previo
                  : firmantes[0]
                    ? clave(firmantes[0])
                    : null,
              )
            }}
          />
          {acciones}
        </div>
      ),
    },
  ]

  // La pestaña de colocar firmas solo aparece cuando hay algo que colocar:
  // un PDF delante y alguien a quien asignarle un recuadro.
  if (urlVista && datos.firmantes.length > 0) {
    pestanas.push({
      id: 'firmas',
      etiqueta: 'Colocar firmas',
      icono: 'file-signature',
      contenido: (
        <div className="form-section">
          <ErrorNotice error={error} />
          <p className="form-section__note">
            Opcional. Elige un firmante y pulsa sobre el documento para colocar su recuadro. Si no
            colocas ninguno, la firma irá solo en la hoja de evidencias del final.
          </p>
          <div
            style={{
              display: 'flex',
              gap: 'var(--sp-2)',
              flexWrap: 'wrap',
              marginBottom: 'var(--sp-2)',
            }}
          >
            {datos.firmantes.map((firmante) => (
              <button
                key={clave(firmante)}
                type="button"
                className={`btn btn--sm${
                  firmanteActivo === clave(firmante) ? ' btn--primary' : ''
                }`}
                onClick={() => setFirmanteActivo(clave(firmante))}
              >
                {firmante.nombre}
                {(posicionesPorFirmante[clave(firmante)]?.length ?? 0) > 0 &&
                  ` (${posicionesPorFirmante[clave(firmante)].length})`}
              </button>
            ))}
          </div>
          <VisorFirmas
            url={urlVista}
            posiciones={(firmanteActivo && posicionesPorFirmante[firmanteActivo]) || []}
            onCambio={(nuevas) => {
              if (!firmanteActivo) return
              setPosicionesPorFirmante((previo) => ({ ...previo, [firmanteActivo]: nuevas }))
            }}
          />
          {acciones}
        </div>
      ),
    })
  }

  return (
    <FichaDetalle
      titulo="Nuevo documento a firmar"
      subtitulo={datos.titulo || 'Sin título todavía'}
      pestanas={pestanas}
      onClose={onCerrar}
    />
  )
}
