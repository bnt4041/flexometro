import { Fragment, useEffect, useMemo, useState } from 'react'
import { Check, Link2, Mail, Save, Send, Trash2, X } from 'lucide-react'

import { CrearTerceroModal } from './CrearTerceroModal'
import { Documentos } from './Documentos'
import { ArbolSolicitud } from './ArbolSolicitud'
import { ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from './ui'
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

  const hayOfertas = solicitud.destinatarios.some((d) => d.ofertas.length > 0)

  /** El precio que tenemos hoy en cada partida del presupuesto: es contra
   *  esto contra lo que se compara una oferta. */
  const precioPorPartida = useMemo(() => {
    const mapa = new Map<string, string>()
    const recorrer = (nodos: NodoCapitulo[]) => {
      for (const nodo of nodos) {
        for (const p of nodo.partidas) mapa.set(p.id, p.precio)
        recorrer(nodo.hijos)
      }
    }
    recorrer(capitulos)
    return mapa
  }, [capitulos])

  /** Las líneas agrupadas por capítulo, para que el comparativo se lea como
   *  un presupuesto y no repita el capítulo en cada fila. Vienen ya ordenadas
   *  por capítulo del servidor. */
  const filasComparativo = useMemo(() => {
    const grupos: { capitulo: string; lineas: typeof solicitud.lineas }[] = []
    for (const linea of solicitud.lineas) {
      const nombre = linea.capitulo_resumen || 'Sin capítulo'
      const ultimo = grupos[grupos.length - 1]
      if (ultimo && ultimo.capitulo === nombre) ultimo.lineas.push(linea)
      else grupos.push({ capitulo: nombre, lineas: [linea] })
    }
    return grupos
  }, [solicitud.lineas])

  /** Totales de lo pedido: el nuestro sobre todas las líneas, y el de cada
   *  proveedor solo sobre las que ha cotizado — por eso se dice cuántas ha
   *  dejado sin cotizar, o los totales no serían comparables. */
  const totales = useMemo(() => {
    let nuestro = 0
    for (const linea of solicitud.lineas) {
      const precio = precioPorPartida.get(linea.partida_id ?? '')
      if (precio) nuestro += Number(precio) * Number(linea.medicion)
    }
    const porProveedor: Record<string, number> = {}
    const sinCotizar: Record<string, number> = {}
    for (const d of solicitud.destinatarios) {
      let suma = 0
      let faltan = 0
      for (const linea of solicitud.lineas) {
        const oferta = d.ofertas.find((o) => o.linea_id === linea.id)
        if (oferta?.precio_ofertado != null) {
          suma += Number(oferta.precio_ofertado) * Number(linea.medicion)
        } else {
          faltan += 1
        }
      }
      porProveedor[d.id] = suma
      sinCotizar[d.id] = faltan
    }
    return { nuestro, porProveedor, sinCotizar }
  }, [solicitud.lineas, solicitud.destinatarios, precioPorPartida])

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
    const ofertadas = d.ofertas.filter((o) => o.precio_ofertado != null).length
    const adjudicadas = d.ofertas.filter((o) => o.aprobada).length
    let aviso = `¿Quitar a ${d.proveedor_razon_social} de esta solicitud?`
    if (d.estado !== 'borrador') {
      aviso += '\n\nSu enlace dejará de funcionar al momento.'
    }
    if (ofertadas > 0) {
      aviso += `\nSe perderán los ${ofertadas} precio${ofertadas === 1 ? '' : 's'} que había puesto.`
    }
    if (adjudicadas > 0) {
      aviso +=
        `\n${adjudicadas} partida${adjudicadas === 1 ? '' : 's'} quedará${adjudicadas === 1 ? '' : 'n'}` +
        ' sin adjudicar, pero el precio que ya se aplicó al presupuesto NO se deshace.'
    }
    if (d.oferta_presupuesto_id) {
      aviso += '\nSu presupuesto de proveedor se conserva.'
    }
    if (!window.confirm(aviso)) return
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
    const conOferta = solicitud.destinatarios.filter((d) =>
      d.ofertas.some((o) => o.precio_ofertado != null),
    ).length
    const conPresupuesto = solicitud.destinatarios.filter((d) => d.oferta_presupuesto_id).length
    let aviso = `¿Eliminar la solicitud «${solicitud.titulo}»?`
    if (solicitud.estado !== 'borrador') {
      aviso += '\n\nLos enlaces de los proveedores dejarán de funcionar al momento.'
    }
    if (conOferta > 0) {
      aviso += `\nSe perderá lo ofertado por ${conOferta} proveedor${conOferta === 1 ? '' : 'es'}.`
    }
    if (conPresupuesto > 0) {
      aviso +=
        `\nLos ${conPresupuesto} presupuesto${conPresupuesto === 1 ? '' : 's'} de proveedor ya` +
        ' generados se conservan, y los precios ya adjudicados no se deshacen.'
    }
    if (!window.confirm(aviso)) return
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
          Marca lo que quieres pedir. Un capítulo entero, partidas sueltas, o —desplegando una
          partida— solo una parte de su descompuesto. Se puede cambiar aunque ya se haya enviado:
          los proveedores verán la lista actualizada la próxima vez que entren, y si ya te habían
          contestado, reenvíales el enlace.
        </p>
        <ArbolSolicitud
          capitulos={capitulos}
          seleccion={{ partidaIds: seleccion, componentes }}
          onCambiarSeleccion={(nueva) => {
            setSeleccion(nueva.partidaIds)
            setComponentes(nueva.componentes)
          }}
        />

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
                    <button
                      className="btn btn--sm"
                      disabled={ocupado !== null}
                      onClick={() => void quitar(d)}
                    >
                      <Trash2 size={14} aria-hidden="true" />
                      Quitar
                    </button>
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
            <p className="form-section__note">
              «Nuestro coste» es lo que tienes presupuestado hoy en cada partida. El porcentaje
              de cada oferta es la diferencia contra ese coste: en verde si te sale más barato.
            </p>
            <div className="table-wrap">
              <table className="table comparativo">
                <thead>
                  <tr>
                    <th>Partida</th>
                    <th className="table__num">Medición</th>
                    <th className="table__num comparativo__nuestro">Nuestro coste</th>
                    {solicitud.destinatarios.map((d) => (
                      <th key={d.id} className="table__num">
                        {d.proveedor_razon_social}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filasComparativo.map(({ capitulo, lineas }) => (
                    <Fragment key={capitulo}>
                      <tr className="separata__capitulo">
                        <td colSpan={3 + solicitud.destinatarios.length}>{capitulo}</td>
                      </tr>
                      {lineas.map((linea) => {
                        const medicion = Number(linea.medicion)
                        const nuestro = precioPorPartida.get(linea.partida_id ?? '') ?? null
                        const celdas = solicitud.destinatarios.map((d) => ({
                          destinatario: d,
                          oferta: d.ofertas.find((o) => o.linea_id === linea.id) ?? null,
                        }))
                        const mejor = celdas
                          .map((c) =>
                            c.oferta?.precio_ofertado != null
                              ? Number(c.oferta.precio_ofertado)
                              : null,
                          )
                          .filter((v): v is number => v !== null)
                          .reduce((min, v) => (min === null || v < min ? v : min), null as number | null)

                        return (
                          <tr key={linea.id}>
                            <td>
                              {linea.resumen}
                              {linea.adjudicada_a_id && (
                                <div className="muted">
                                  Adjudicada a{' '}
                                  {solicitud.destinatarios.find(
                                    (d) => d.id === linea.adjudicada_a_id,
                                  )?.proveedor_razon_social ?? 'un proveedor'}
                                </div>
                              )}
                            </td>
                            <td className="table__num">
                              {linea.medicion} <span className="muted">{linea.unidad}</span>
                            </td>
                            <td className="table__num comparativo__nuestro">
                              {nuestro !== null ? (
                                <>
                                  {formatoImporte(nuestro)} €
                                  <div className="muted">
                                    {formatoImporte(Number(nuestro) * medicion)} €
                                  </div>
                                </>
                              ) : (
                                <span className="muted">—</span>
                              )}
                            </td>
                            {celdas.map(({ destinatario, oferta }) => {
                              if (!oferta || oferta.precio_ofertado == null) {
                                return (
                                  <td key={destinatario.id} className="table__num muted">
                                    —
                                  </td>
                                )
                              }
                              const precio = Number(oferta.precio_ofertado)
                              const esMejor = mejor !== null && precio === mejor
                              const adjudicadaAOtro =
                                linea.adjudicada_a_id != null &&
                                linea.adjudicada_a_id !== destinatario.id
                              const diferencia =
                                nuestro !== null && Number(nuestro) > 0
                                  ? ((precio - Number(nuestro)) / Number(nuestro)) * 100
                                  : null

                              return (
                                <td
                                  key={destinatario.id}
                                  className={
                                    esMejor ? 'table__num comparativo__mejor' : 'table__num'
                                  }
                                >
                                  <div className="comparativo__precio">
                                    {formatoImporte(oferta.precio_ofertado)} €
                                  </div>
                                  <div className="muted">
                                    {formatoImporte(precio * medicion)} €
                                  </div>
                                  {diferencia !== null && (
                                    <div
                                      className={
                                        diferencia <= 0
                                          ? 'comparativo__dif comparativo__dif--baja'
                                          : 'comparativo__dif comparativo__dif--alta'
                                      }
                                    >
                                      {diferencia > 0 ? '+' : ''}
                                      {diferencia.toFixed(1)} %
                                    </div>
                                  )}
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
                                  {oferta.observaciones_proveedor && (
                                    <div className="muted comparativo__obs">
                                      {oferta.observaciones_proveedor}
                                    </div>
                                  )}
                                </td>
                              )
                            })}
                          </tr>
                        )
                      })}
                    </Fragment>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td colSpan={2}>
                      <strong>Total de lo pedido</strong>
                    </td>
                    <td className="table__num comparativo__nuestro">
                      <strong>{formatoImporte(totales.nuestro)} €</strong>
                    </td>
                    {solicitud.destinatarios.map((d) => (
                      <td key={d.id} className="table__num">
                        <strong>{formatoImporte(totales.porProveedor[d.id] ?? 0)} €</strong>
                        {totales.sinCotizar[d.id] > 0 && (
                          <div className="muted">
                            {totales.sinCotizar[d.id]} sin cotizar
                          </div>
                        )}
                      </td>
                    ))}
                  </tr>
                </tfoot>
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
        <button className="btn" disabled={ocupado !== null} onClick={() => void eliminar()}>
          <Trash2 size={16} aria-hidden="true" />
          {ocupado === 'eliminar' ? 'Eliminando…' : 'Eliminar solicitud'}
        </button>
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
