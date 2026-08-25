import { useEffect, useState } from 'react'
import { Check, Link2, Mail, Save, Send, Trash2, X } from 'lucide-react'

import { CrearTerceroModal } from './CrearTerceroModal'
import { Documentos } from './Documentos'
import { Checkbox, ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type {
  ComponentePedido,
  NodoCapitulo,
  SolicitudDestinatario,
  SolicitudPrecios,
  Tercero,
} from '../lib/api'
import { useToast } from '../toast'

export const ETIQUETA_ESTADO_SOLICITUD: Record<string, string> = {
  borrador: 'Borrador',
  enviada: 'Enviada',
  respondida: 'Respondida',
  aprobada: 'Aprobada',
  descartada: 'Descartada',
  caducada: 'Caducada',
}

interface GrupoPartidas {
  capituloResumen: string
  partidas: { id: string; resumen: string; unidad: string }[]
}

function agruparPorCapitulo(capitulos: NodoCapitulo[]): GrupoPartidas[] {
  const grupos: GrupoPartidas[] = []
  function recorrer(nodos: NodoCapitulo[]) {
    for (const nodo of nodos) {
      if (nodo.partidas.length > 0) {
        grupos.push({
          capituloResumen: nodo.resumen,
          partidas: nodo.partidas.map((p) => ({ id: p.id, resumen: p.resumen, unidad: p.unidad })),
        })
      }
      recorrer(nodo.hijos)
    }
  }
  recorrer(capitulos)
  return grupos
}

/** Ficha de un paquete de solicitud de precios ("Yeserías"): qué se pide, a
 *  quién, y qué ha ofertado cada uno.
 *
 *  Las partidas son editables siempre, también con el paquete ya enviado;
 *  quien lo manda decide si reenvía a los proveedores anteriores. Por eso el
 *  comparativo puede tener huecos: un proveedor que no llegó a ver una línea
 *  simplemente no la tiene ofertada. */
export function SolicitudFicha({
  solicitud,
  capitulos,
  onClose,
  onCambio,
  onAprobado,
}: {
  solicitud: SolicitudPrecios
  capitulos: NodoCapitulo[]
  onClose: () => void
  onCambio: () => void
  onAprobado: () => void
}) {
  const { notificar } = useToast()

  const [titulo, setTitulo] = useState(solicitud.titulo)
  const [notas, setNotas] = useState(solicitud.notas ?? '')
  const [seleccion, setSeleccion] = useState<Set<string>>(
    new Set(
      solicitud.lineas
        .filter((l) => l.concepto_id == null)
        .map((l) => l.partida_id)
        .filter((id): id is string => id != null),
    ),
  )
  const [componentes, setComponentes] = useState<ComponentePedido[]>(
    solicitud.lineas
      .filter((l) => l.concepto_id != null && l.partida_id != null)
      .map((l) => ({ partida_id: l.partida_id as string, concepto_id: l.concepto_id as string })),
  )
  const [enlaces, setEnlaces] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState<string | null>(null)
  const [anadiendo, setAnadiendo] = useState(false)

  const grupos = agruparPorCapitulo(capitulos)
  const hayOfertas = solicitud.destinatarios.some((d) => d.ofertas.length > 0)

  function alternar(partidaId: string) {
    setSeleccion((actual) => {
      const nueva = new Set(actual)
      if (nueva.has(partidaId)) nueva.delete(partidaId)
      else nueva.add(partidaId)
      return nueva
    })
  }

  async function conAviso(clave: string, accion: () => Promise<void>) {
    setOcupado(clave)
    setError(null)
    try {
      await accion()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(null)
    }
  }

  async function guardar() {
    if (seleccion.size === 0 && componentes.length === 0) {
      setError('Elige al menos una partida o un componente')
      return
    }
    await conAviso('guardar', async () => {
      await api.solicitudesPrecios.actualizarLineas(solicitud.id, {
        partida_ids: [...seleccion],
        componentes,
      })
      await api.solicitudesPrecios.update(solicitud.id, {
        titulo: titulo.trim() || solicitud.titulo,
        notas: notas || null,
      })
      notificar('Solicitud guardada')
      onCambio()
    })
  }

  async function copiar(texto: string) {
    try {
      await navigator.clipboard.writeText(texto)
      notificar('Enlace copiado al portapapeles')
    } catch {
      // Sin permiso de portapapeles queda visible en pantalla para copiarlo
      // a mano — el enlace no se pierde por esto.
      notificar('Copia el enlace de la tabla a mano', 'error')
    }
  }

  async function enviarA(d: SolicitudDestinatario) {
    const reenvio = d.estado !== 'borrador'
    if (
      reenvio &&
      !window.confirm(
        `Se le manda un enlace NUEVO a ${d.proveedor_razon_social} y el anterior deja de ` +
          'funcionar. Lo que ya hubiera rellenado se conserva. ¿Continuar?',
      )
    ) {
      return
    }
    await conAviso(`enviar:${d.id}`, async () => {
      const { enlace } = await api.solicitudesPrecios.destinatarios.enviar(solicitud.id, d.id)
      setEnlaces((e) => ({ ...e, [d.id]: enlace }))
      notificar(`Enviado a ${d.proveedor_razon_social}`)
      onCambio()
    })
  }

  async function enlazar(d: SolicitudDestinatario) {
    if (enlaces[d.id]) {
      await copiar(enlaces[d.id])
      return
    }
    if (
      d.estado !== 'borrador' &&
      !window.confirm(
        'Se generará un enlace NUEVO y el anterior dejará de funcionar. ' +
          'Lo que ya hubiera rellenado se conserva. ¿Continuar?',
      )
    ) {
      return
    }
    await conAviso(`enlace:${d.id}`, async () => {
      const { enlace } = await api.solicitudesPrecios.destinatarios.generarEnlace(
        solicitud.id,
        d.id,
      )
      setEnlaces((e) => ({ ...e, [d.id]: enlace }))
      await copiar(enlace)
      onCambio()
    })
  }

  async function quitar(d: SolicitudDestinatario) {
    if (!window.confirm(`¿Quitar a ${d.proveedor_razon_social} de esta solicitud?`)) return
    await conAviso(`quitar:${d.id}`, async () => {
      await api.solicitudesPrecios.destinatarios.remove(solicitud.id, d.id)
      notificar(`${d.proveedor_razon_social} quitado`)
      onCambio()
    })
  }

  async function cambiarCorreo(d: SolicitudDestinatario, valor: string) {
    await conAviso(`correo:${d.id}`, async () => {
      await api.solicitudesPrecios.destinatarios.update(solicitud.id, d.id, {
        email_destino: valor && valor !== d.proveedor_email ? valor : null,
      })
      onCambio()
    })
  }

  async function aprobar(ofertaId: string) {
    await conAviso(`aprobar:${ofertaId}`, async () => {
      await api.solicitudesPrecios.aprobarOferta(ofertaId)
      notificar('Adjudicada: el precio se ha aplicado sobre la partida')
      onAprobado()
      onCambio()
    })
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar la solicitud «${solicitud.titulo}»?`)) return
    await conAviso('eliminar', async () => {
      await api.solicitudesPrecios.remove(solicitud.id)
      notificar('Solicitud eliminada')
      onCambio()
      onClose()
    })
  }

  return (
    <ModalPantalla
      title={`${solicitud.titulo} · ${solicitud.codigo}`}
      onClose={onClose}
    >
      <div className="form-section">
        <ErrorNotice error={error} />

        {/* --- 1. Datos --- */}
        <div className="form-grid">
          <Field ancho="doble" label="Nombre">
            <input className="input" value={titulo} onChange={(e) => setTitulo(e.target.value)} />
          </Field>
          <Field label="Estado">
            <span className={`chip chip--estado-${solicitud.estado}`}>
              {ETIQUETA_ESTADO_SOLICITUD[solicitud.estado] ?? solicitud.estado}
            </span>
          </Field>
        </div>
        <Field label="Notas para los proveedores (opcional)">
          <textarea
            className="input"
            rows={2}
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
          />
        </Field>

        {/* --- 2. Partidas --- */}
        <p className="field__label" style={{ marginTop: 'var(--sp-4)' }}>
          Partidas
        </p>
        <p className="form-section__note">
          Se pueden cambiar aunque ya se haya enviado. Los proveedores verán la lista actualizada
          la próxima vez que entren; si ya te habían contestado, reenvíales el enlace.
        </p>
        {grupos.map((grupo) => (
          <div key={grupo.capituloResumen} style={{ marginBottom: 'var(--sp-3)' }}>
            <p className="muted" style={{ marginBottom: 'var(--sp-1)' }}>
              {grupo.capituloResumen}
            </p>
            {grupo.partidas.map((p) => (
              <Checkbox
                key={p.id}
                label={`${p.resumen} (${p.unidad})`}
                checked={seleccion.has(p.id)}
                onChange={() => alternar(p.id)}
              />
            ))}
          </div>
        ))}

        {componentes.length > 0 && (
          <>
            <p className="field__label">Componentes de descompuesto</p>
            <p className="form-section__note">
              Se piden desde el descompuesto de una partida. Aquí solo se pueden quitar.
            </p>
            <ul className="chat-ia__componentes">
              {solicitud.lineas
                .filter((l) => l.concepto_id != null)
                .map((l) => {
                  const sigue = componentes.some((c) => c.concepto_id === l.concepto_id)
                  return (
                    <li key={l.id}>
                      {l.resumen} ({l.unidad}){' '}
                      <button
                        className="btn btn--sm"
                        disabled={!sigue}
                        onClick={() =>
                          setComponentes((actual) =>
                            actual.filter((c) => c.concepto_id !== l.concepto_id),
                          )
                        }
                      >
                        {sigue ? 'Quitar' : 'Quitado'}
                      </button>
                    </li>
                  )
                })}
            </ul>
          </>
        )}

        <div className="form-actions" style={{ marginBottom: 'var(--sp-5)' }}>
          <button className="btn btn--primary" disabled={ocupado !== null} onClick={() => void guardar()}>
            {ocupado !== 'guardar' && <Save size={16} aria-hidden="true" />}
            {ocupado === 'guardar' ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>

        {/* --- 3. Proveedores --- */}
        <p className="field__label">Proveedores</p>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Proveedor</th>
                <th>Enviar a</th>
                <th>Estado</th>
                <th>Ofertadas</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {solicitud.destinatarios.map((d) => (
                <tr key={d.id}>
                  <td>
                    <strong>{d.proveedor_razon_social}</strong>
                    {enlaces[d.id] && (
                      <input
                        className="input"
                        readOnly
                        value={enlaces[d.id]}
                        onFocus={(e) => e.target.select()}
                        style={{ marginTop: 'var(--sp-1)' }}
                      />
                    )}
                  </td>
                  <td>
                    <input
                      className="input"
                      type="email"
                      defaultValue={d.email_destino ?? d.proveedor_email ?? ''}
                      placeholder="sin correo"
                      onBlur={(e) => void cambiarCorreo(d, e.target.value)}
                    />
                  </td>
                  <td>
                    <span className={`chip chip--estado-${d.estado}`}>
                      {ETIQUETA_ESTADO_SOLICITUD[d.estado] ?? d.estado}
                    </span>
                  </td>
                  <td className="table__num">
                    {d.ofertas.filter((o) => o.precio_ofertado != null).length || '—'}
                  </td>
                  <td className="table__actions">
                    <Tooltip texto={d.estado === 'borrador' ? 'Mandarle el enlace por correo' : 'Reenviar con un enlace nuevo'}>
                      <button
                        className="btn btn--sm"
                        disabled={ocupado !== null}
                        onClick={() => void enviarA(d)}
                      >
                        <Mail size={14} aria-hidden="true" />
                        {ocupado === `enviar:${d.id}`
                          ? 'Enviando…'
                          : d.estado === 'borrador'
                            ? 'Enviar'
                            : 'Reenviar'}
                      </button>
                    </Tooltip>{' '}
                    <Tooltip texto="Generar el enlace para pasárselo tú">
                      <button
                        className="btn btn--sm"
                        disabled={ocupado !== null}
                        onClick={() => void enlazar(d)}
                      >
                        <Link2 size={14} aria-hidden="true" />
                        {ocupado === `enlace:${d.id}` ? 'Generando…' : 'Enlace'}
                      </button>
                    </Tooltip>{' '}
                    {d.estado === 'borrador' && (
                      <button
                        className="btn btn--sm"
                        disabled={ocupado !== null}
                        onClick={() => void quitar(d)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                        Quitar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button
          className="btn btn--sm"
          style={{ marginTop: 'var(--sp-2)' }}
          onClick={() => setAnadiendo(true)}
        >
          <Send size={14} aria-hidden="true" />
          Añadir proveedor…
        </button>

        {/* --- 4. Comparativo --- */}
        {hayOfertas && (
          <>
            <p className="field__label" style={{ marginTop: 'var(--sp-5)' }}>
              Comparativo
            </p>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Partida</th>
                    <th>Medición</th>
                    {solicitud.destinatarios.map((d) => (
                      <th key={d.id}>{d.proveedor_razon_social}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {solicitud.lineas.map((linea) => {
                    const celdas = solicitud.destinatarios.map((d) => ({
                      destinatario: d,
                      oferta: d.ofertas.find((o) => o.linea_id === linea.id) ?? null,
                    }))
                    const mejor = celdas
                      .map((c) =>
                        c.oferta?.precio_ofertado ? Number(c.oferta.precio_ofertado) : null,
                      )
                      .filter((v): v is number => v !== null)
                      .reduce((min, v) => (min === null || v < min ? v : min), null as number | null)

                    return (
                      <tr key={linea.id}>
                        <td>
                          <span className="muted">{linea.capitulo_resumen}</span>
                          <br />
                          {linea.resumen}
                        </td>
                        <td className="table__num">
                          {linea.medicion} {linea.unidad}
                        </td>
                        {celdas.map(({ destinatario, oferta }) => {
                          if (!oferta || oferta.precio_ofertado == null) {
                            return (
                              <td key={destinatario.id} className="muted">
                                —
                              </td>
                            )
                          }
                          const esMejor =
                            mejor !== null && Number(oferta.precio_ofertado) === mejor
                          const adjudicadaAOtro =
                            linea.adjudicada_a_id != null &&
                            linea.adjudicada_a_id !== destinatario.id
                          return (
                            <td key={destinatario.id}>
                              <div
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 'var(--sp-2)',
                                  fontWeight: esMejor ? 600 : undefined,
                                }}
                              >
                                <span className="table__num">
                                  {formatoImporte(oferta.precio_ofertado)} €
                                </span>
                                {oferta.aprobada ? (
                                  <span className="badge badge--success">
                                    <Check size={12} aria-hidden="true" /> Adjudicada
                                  </span>
                                ) : (
                                  !adjudicadaAOtro && (
                                    <Tooltip texto="Aplica este precio sobre la partida del presupuesto">
                                      <button
                                        className="btn btn--sm"
                                        disabled={ocupado !== null}
                                        onClick={() => void aprobar(oferta.id)}
                                      >
                                        {ocupado === `aprobar:${oferta.id}`
                                          ? 'Adjudicando…'
                                          : 'Adjudicar'}
                                      </button>
                                    </Tooltip>
                                  )
                                )}
                              </div>
                              {oferta.observaciones_proveedor && (
                                <div className="muted">{oferta.observaciones_proveedor}</div>
                              )}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}

        {/* --- 5. Documentos --- */}
        <p className="field__label" style={{ marginTop: 'var(--sp-5)' }}>
          Documentos para los proveedores
        </p>
        <p className="form-section__note">
          Los ven y se los descargan desde su enlace, sin necesidad de cuenta.
        </p>
        <Documentos entidad="solicitud_precios" entidadId={solicitud.id} />
      </div>

      <div className="form-actions">
        {solicitud.estado === 'borrador' && (
          <button className="btn" disabled={ocupado !== null} onClick={() => void eliminar()}>
            <Trash2 size={16} aria-hidden="true" />
            {ocupado === 'eliminar' ? 'Eliminando…' : 'Eliminar solicitud'}
          </button>
        )}
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cerrar
        </button>
      </div>

      {anadiendo && (
        <AnadirProveedorModal
          yaElegidos={solicitud.destinatarios.map((d) => d.proveedor_id)}
          onClose={() => setAnadiendo(false)}
          onElegido={(p) =>
            void conAviso('anadir', async () => {
              await api.solicitudesPrecios.destinatarios.add(solicitud.id, { proveedor_id: p.id })
              notificar(`${p.razon_social} añadido`)
              setAnadiendo(false)
              onCambio()
            })
          }
        />
      )}
    </ModalPantalla>
  )
}

/** Picker de proveedor con alta al vuelo, para sumar destinatarios a un
 *  paquete que ya existe. */
function AnadirProveedorModal({
  yaElegidos,
  onClose,
  onElegido,
}: {
  yaElegidos: string[]
  onClose: () => void
  onElegido: (proveedor: Tercero) => void
}) {
  const [proveedores, setProveedores] = useState<Tercero[]>([])
  const [creando, setCreando] = useState(false)

  useEffect(() => {
    void api.terceros
      .list({ rol: 'proveedor', activo: true, limit: 500 })
      .then((p) => setProveedores(p.items))
  }, [])

  const disponibles = proveedores.filter((p) => !yaElegidos.includes(p.id))

  return (
    <Modal title="Añadir proveedor" onClose={onClose}>
      <div className="form-section">
        <Field label="Proveedor">
          <select
            className="select"
            value=""
            onChange={(e) => {
              if (e.target.value === '__nuevo__') {
                setCreando(true)
                return
              }
              const proveedor = disponibles.find((p) => p.id === e.target.value)
              if (proveedor) onElegido(proveedor)
            }}
          >
            <option value="">Elige un proveedor…</option>
            {disponibles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.razon_social}
              </option>
            ))}
            <option value="__nuevo__">+ Nuevo proveedor…</option>
          </select>
        </Field>
      </div>
      {creando && (
        <CrearTerceroModal
          rolPorDefecto="proveedor"
          onClose={() => setCreando(false)}
          onCreado={(tercero) => {
            setCreando(false)
            onElegido(tercero)
          }}
        />
      )}
    </Modal>
  )
}
