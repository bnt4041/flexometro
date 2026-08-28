import { useState } from 'react'
import { Check, Sparkles, X } from 'lucide-react'

import { ErrorNotice, Modal } from './ui'
import { api } from '../lib/api'
import type {
  AlcancePegado,
  NaturalezaConcepto,
  PartidaConComponentes,
  PropuestaIA,
  ResultadoPegado,
} from '../lib/api'

interface Mensaje {
  rol: 'user' | 'assistant'
  contenido: string
}

type Propuesta = PropuestaIA

/** Contexto mínimo, sin el id/código del documento (pedido o factura): quien
 *  monta este componente cierra ese dato dentro de `conversar` (ver
 *  `PedidoDetalle`/`FacturaDetalle`), así que aquí no hace falta distinguir
 *  `pedido_id` de `factura_id`. */
export interface ContextoAyudaDocumento {
  tipo: 'capitulo' | 'partida'
  codigo?: string | null
  resumen: string
  unidad?: string | null
  precio?: string | null
}

/** Hermano generalizado de `AyudaIAModal.tsx` (Fase 4 del plan "Capítulos,
 *  partidas y mediciones en Pedidos y Facturas") para Pedido de CLIENTE y
 *  Factura de venta — mismo chat, misma tarjeta de propuesta y el mismo
 *  criterio de nunca ejecutar nada sin que el usuario confirme, pero sin
 *  asumir `api.presupuestos.*`/`api.capitulos.*`/`api.partidas.*` fijos: todo
 *  lo que escribe de verdad (conversar, aplicar un capítulo, copiar o crear
 *  una partida, añadir un componente) llega inyectado por props, para poder
 *  montarse igual sobre `api.pedidos`/`api.pedidosCapitulos`/
 *  `api.pedidosPartidas` o sobre `api.facturas`/`api.facturasCapitulos`/
 *  `api.facturasPartidas` según toque. No se generalizó `AyudaIAModal.tsx`
 *  in-place para no arriesgar su uso ya en producción en presupuestos —
 *  mismo criterio ya usado con `DescompuestoDocumento.tsx` frente a
 *  `DescompuestoPartida.tsx`. */
export function AyudaIADocumentoModal({
  contexto,
  destinoCapituloId,
  conversar,
  aplicarCapitulo,
  pegarPartida,
  crearPartida,
  anadirComponente,
  onCambio,
  onClose,
}: {
  contexto: ContextoAyudaDocumento
  /** Capítulo donde iría una partida propuesta (copiada o nueva) si se
   *  confirma — el de la partida seleccionada desde la que se abrió esta
   *  conversación. */
  destinoCapituloId: string | null
  conversar: (datos: {
    contexto: ContextoAyudaDocumento
    mensajes: Mensaje[]
  }) => Promise<{ respuesta: string; propuesta: Propuesta | null }>
  /** Un capítulo propuesto por vez (varias llamadas en secuencia si la
   *  propuesta trae varios) — equivalente a `api.pedidos.iaAplicarCapitulo`/
   *  `api.facturas.iaAplicarCapitulo`. */
  aplicarCapitulo: (datos: {
    capitulo_resumen: string
    partidas: PartidaConComponentes[]
  }) => Promise<{ id: string; resumen: string; partidas: number }>
  /** Equivalente a `api.pedidosCapitulos.pegarPartidas`/
   *  `api.facturasCapitulos.pegarPartidas`. */
  pegarPartida: (
    capituloId: string,
    datos: { partida_ids: string[]; alcance: AlcancePegado },
  ) => Promise<ResultadoPegado>
  /** Equivalente a `api.pedidosCapitulos.addPartida`/
   *  `api.facturasCapitulos.addPartida` — solo hace falta el id de vuelta. */
  crearPartida: (
    capituloId: string,
    datos: { resumen: string; unidad: string; precio: string },
  ) => Promise<{ id: string }>
  /** Equivalente a `api.pedidosPartidas.anadirComponente`/
   *  `api.facturasPartidas.anadirComponente`. */
  anadirComponente: (
    partidaId: string,
    datos: { hijo_id: string; rendimiento: string },
  ) => Promise<unknown>
  onCambio: () => void
  onClose: () => void
}) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([])
  const [entrada, setEntrada] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [propuesta, setPropuesta] = useState<Propuesta | null>(null)
  const [confirmando, setConfirmando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function enviar() {
    const texto = entrada.trim()
    if (texto === '' || enviando) return
    setError(null)
    setPropuesta(null)
    const historial = [...mensajes, { rol: 'user' as const, contenido: texto }]
    setMensajes(historial)
    setEntrada('')
    setEnviando(true)
    try {
      const { respuesta, propuesta: nueva } = await conversar({
        contexto,
        mensajes: historial.map((m) => ({ rol: m.rol, contenido: m.contenido })),
      })
      setMensajes((actual) => [...actual, { rol: 'assistant', contenido: respuesta }])
      if (nueva) setPropuesta(nueva)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  async function confirmarCopiar(alcance: AlcancePegado) {
    if (!propuesta?.partida_id || !destinoCapituloId) return
    const resultado = await pegarPartida(destinoCapituloId, {
      partida_ids: [propuesta.partida_id],
      alcance,
    })
    return resultado.pegadas === 1
      ? 'Hecho: partida copiada aquí.'
      : 'No se ha podido copiar (puede que ya no exista o no sea de esta cuenta).'
  }

  async function confirmarCrear() {
    if (!propuesta?.resumen || !propuesta.unidad || !destinoCapituloId) return
    // La misma partida en dos pasos: se crea vacía (como el botón "+
    // Partida") y luego se le añaden sus componentes uno a uno (como el "+
    // Línea" del descompuesto) — nada que no se pudiera hacer ya a mano. Un
    // componente personalizado necesita un paso previo: darlo de alta en el
    // banco de precios (como haría el usuario a mano desde esa pantalla)
    // antes de poder añadirlo igual que cualquier otro — el banco de precios
    // es el mismo para toda la cuenta, así que esto sí es `api.conceptos.create`
    // directo, no una función inyectada.
    const nueva = await crearPartida(destinoCapituloId, {
      resumen: propuesta.resumen,
      unidad: propuesta.unidad,
      precio: '0',
    })
    for (const c of propuesta.componentes) {
      const hijoId = c.personalizado
        ? (
            await api.conceptos.create({
              tipo: 'basico',
              naturaleza: (c.naturaleza as NaturalezaConcepto) ?? 'sin_clasificar',
              unidad: c.unidad,
              resumen: c.resumen,
              precio: c.precio ?? '0',
              origen_precio: 'manual',
              origen_dato: 'ia',
            })
          ).id
        : c.concepto_id!
      await anadirComponente(nueva.id, {
        hijo_id: hijoId,
        rendimiento: c.rendimiento,
      })
    }
    return `Hecho: partida «${propuesta.resumen}» creada con ${propuesta.componentes.length} componente${propuesta.componentes.length === 1 ? '' : 's'}.`
  }

  async function confirmarCapitulos() {
    if (!propuesta || propuesta.capitulos_propuestos.length === 0) return
    // Un capítulo por llamada, en secuencia (no en paralelo: cada uno hace
    // su propio commit y dos peticiones a la vez podrían pisarse el orden)
    // — pero de cara al usuario es un solo "Confirmar".
    const hechos: string[] = []
    for (const capitulo of propuesta.capitulos_propuestos) {
      const resultado = await aplicarCapitulo({
        capitulo_resumen: capitulo.resumen,
        partidas: capitulo.partidas,
      })
      hechos.push(`«${resultado.resumen}» (${resultado.partidas} partida${resultado.partidas === 1 ? '' : 's'})`)
    }
    return `Hecho: capítulo${hechos.length === 1 ? '' : 's'} creado${hechos.length === 1 ? '' : 's'} ${hechos.join(', ')}.`
  }

  async function confirmarPropuesta(alcance: AlcancePegado) {
    if (!propuesta || confirmando) return
    setConfirmando(true)
    setError(null)
    try {
      const texto =
        propuesta.tipo === 'copiar_partida'
          ? await confirmarCopiar(alcance)
          : propuesta.tipo === 'crear_capitulos'
            ? await confirmarCapitulos()
            : await confirmarCrear()
      setPropuesta(null)
      if (texto) setMensajes((actual) => [...actual, { rol: 'assistant', contenido: texto }])
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setConfirmando(false)
    }
  }

  return (
    <Modal title="Ayuda con IA" onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          Sobre <strong>«{contexto.resumen}»</strong> — puede buscar en cualquier pedido/factura o el
          banco de precios de la cuenta.
        </p>

        {mensajes.length > 0 && (
          <div className="chat-ia">
            {mensajes.map((m, i) => (
              <div key={i} className={m.rol === 'user' ? 'chat-ia__burbuja is-usuario' : 'chat-ia__burbuja'}>
                {m.contenido}
              </div>
            ))}
            {enviando && <div className="chat-ia__burbuja muted">Consultando a DeepSeek…</div>}
          </div>
        )}

        {propuesta && (
          <div className="chat-ia__propuesta">
            <p>{propuesta.descripcion}</p>
            {propuesta.tipo === 'crear_partida' && propuesta.componentes.length > 0 && (
              <ul className="chat-ia__componentes">
                {propuesta.componentes.map((c, i) => (
                  <li key={c.concepto_id ?? i}>
                    {c.rendimiento} {c.unidad} — {c.personalizado ? (
                      <>
                        {c.resumen} · <strong>personalizado, {c.precio} €</strong>
                      </>
                    ) : (
                      <>
                        {c.codigo} · {c.resumen}
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {propuesta.tipo === 'crear_capitulos' && propuesta.capitulos_propuestos.length > 0 && (
              <div className="chat-ia__capitulos">
                {propuesta.capitulos_propuestos.map((cap, k) => (
                  <div key={k} className="chat-ia__capitulo">
                    <strong>{cap.resumen}</strong>
                    <ul className="chat-ia__componentes">
                      {cap.partidas.map((p, i) => (
                        <li key={p.partida_id ?? i}>
                          <strong>
                            {p.resumen} {p.unidad ? `(${p.unidad})` : ''}
                          </strong>
                          {p.partida_id ? (
                            <span className="muted"> · ya existe, se mueve aquí</span>
                          ) : (
                            <ul className="chat-ia__componentes">
                              {p.componentes.map((c, j) => (
                                <li key={c.concepto_id ?? j}>
                                  {c.rendimiento} {c.unidad} —{' '}
                                  {c.personalizado ? (
                                    <>
                                      {c.resumen} · <strong>personalizado, {c.precio} €</strong>
                                    </>
                                  ) : (
                                    <>
                                      {c.codigo} · {c.resumen}
                                    </>
                                  )}
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            )}
            {propuesta.tipo === 'crear_capitulos' ? (
              // Crea capítulos nuevos: no depende de la fila desde la que se
              // abrió esta conversación, a diferencia de copiar/crear una
              // partida suelta (que van al capítulo de destino).
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                <button
                  className="btn btn--sm"
                  disabled={confirmando}
                  onClick={() => void confirmarPropuesta('copiar')}
                >
                  <Check size={14} aria-hidden="true" />
                  {propuesta.capitulos_propuestos.length === 1
                    ? 'Confirmar y crear capítulo'
                    : `Confirmar los ${propuesta.capitulos_propuestos.length} capítulos`}
                </button>
                <button className="btn btn--sm" disabled={confirmando} onClick={() => setPropuesta(null)}>
                  <X size={14} aria-hidden="true" />
                  Descartar
                </button>
              </div>
            ) : destinoCapituloId ? (
              <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                <button
                  className="btn btn--sm"
                  disabled={confirmando}
                  onClick={() => void confirmarPropuesta('copiar')}
                >
                  <Check size={14} aria-hidden="true" />
                  {propuesta.tipo === 'copiar_partida' ? 'Confirmar y copiar aquí' : 'Confirmar y crear aquí'}
                </button>
                <button
                  className="btn btn--sm"
                  disabled={confirmando}
                  onClick={() => setPropuesta(null)}
                >
                  <X size={14} aria-hidden="true" />
                  Descartar
                </button>
              </div>
            ) : (
              <p className="muted">
                No hay un capítulo de destino claro aquí — abre esta ayuda desde una partida para poder
                confirmarlo.
              </p>
            )}
          </div>
        )}

        <ErrorNotice error={error} />

        <label className="field">
          <span className="field__label">Mensaje</span>
          <textarea
            className="input"
            rows={2}
            placeholder="¿Qué quieres saber o buscar?"
            value={entrada}
            onChange={(e) => setEntrada(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void enviar()
              }
            }}
            autoFocus
          />
        </label>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cerrar
        </button>
        <button className="btn btn--primary" disabled={enviando || entrada.trim() === ''} onClick={() => void enviar()}>
          {!enviando && <Sparkles size={16} aria-hidden="true" />}
          {enviando ? 'Consultando a DeepSeek…' : 'Enviar'}
        </button>
      </div>
    </Modal>
  )
}
