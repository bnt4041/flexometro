import { useEffect, useState } from 'react'
import { Check, Copy, Link2, Mail, Save, Trash2, X } from 'lucide-react'

import { CrearTerceroModal } from './CrearTerceroModal'
import { Documentos } from './Documentos'
import { Checkbox, ErrorNotice, Field, Modal, Tooltip, formatoImporte } from './ui'
import { api } from '../lib/api'
import type { NodoCapitulo, SolicitudPrecios, Tercero } from '../lib/api'
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

/** Ficha de UNA solicitud de precios (Fase 53): el ciclo de vida entero de
 *  una petición a un proveedor, desde el borrador editable hasta la oferta
 *  recibida y aprobada.
 *
 *  Mientras es borrador se puede tocar todo (partidas, notas, documentos);
 *  en cuanto sale — por correo o por enlace — sus líneas quedan congeladas
 *  en lo que ve el proveedor, y lo que queda es recibir precios y aprobarlos. */
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
  const esBorrador = solicitud.estado === 'borrador'

  const [seleccion, setSeleccion] = useState<Set<string>>(
    new Set(solicitud.lineas.map((l) => l.partida_id).filter((id): id is string => id != null)),
  )
  const [notas, setNotas] = useState(solicitud.notas ?? '')
  const [enlace, setEnlace] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState<
    'guardando' | 'enviando' | 'enlace' | 'eliminando' | 'aprobando' | null
  >(null)
  const [aprobandoLinea, setAprobandoLinea] = useState<string | null>(null)
  const [duplicando, setDuplicando] = useState(false)

  const grupos = agruparPorCapitulo(capitulos)

  function alternar(partidaId: string) {
    setSeleccion((actual) => {
      const nueva = new Set(actual)
      if (nueva.has(partidaId)) nueva.delete(partidaId)
      else nueva.add(partidaId)
      return nueva
    })
  }

  async function guardarCambios(): Promise<boolean> {
    if (seleccion.size === 0) {
      setError('Elige al menos una partida')
      return false
    }
    setError(null)
    try {
      await api.solicitudesPrecios.actualizarLineas(solicitud.id, [...seleccion])
      await api.solicitudesPrecios.update(solicitud.id, { notas: notas || null })
      return true
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      return false
    }
  }

  async function guardar() {
    setOcupado('guardando')
    const ok = await guardarCambios()
    setOcupado(null)
    if (!ok) return
    notificar('Borrador guardado')
    onCambio()
  }

  async function enviarPorCorreo() {
    setOcupado('enviando')
    if (esBorrador && !(await guardarCambios())) {
      setOcupado(null)
      return
    }
    try {
      const resultado = await api.solicitudesPrecios.enviar(solicitud.id)
      setEnlace(resultado.enlace)
      notificar(`Solicitud enviada a ${solicitud.proveedor_razon_social}`)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(null)
    }
  }

  async function copiarEnlace() {
    // Si acabamos de emitirlo en esta misma sesión (al enviar el correo, o de
    // una copia anterior), se reutiliza: pedir otro invalidaría el que el
    // proveedor ya tiene.
    if (enlace) {
      await alPortapapeles(enlace)
      return
    }
    if (
      !esBorrador &&
      !window.confirm(
        'Se generará un enlace NUEVO y el anterior dejará de funcionar ' +
          '(el que ya se envió no se puede recuperar). ¿Continuar?',
      )
    ) {
      return
    }
    setOcupado('enlace')
    if (esBorrador && !(await guardarCambios())) {
      setOcupado(null)
      return
    }
    try {
      const { enlace: nuevo } = await api.solicitudesPrecios.generarEnlace(solicitud.id)
      setEnlace(nuevo)
      await alPortapapeles(nuevo)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(null)
    }
  }

  async function alPortapapeles(texto: string) {
    try {
      await navigator.clipboard.writeText(texto)
      notificar('Enlace copiado al portapapeles')
    } catch {
      // Sin permiso de portapapeles queda visible en pantalla para copiarlo
      // a mano — el enlace no se pierde por esto.
      notificar('Copia el enlace de abajo a mano', 'error')
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar el borrador para «${solicitud.proveedor_razon_social}»?`)) return
    setOcupado('eliminando')
    setError(null)
    try {
      await api.solicitudesPrecios.remove(solicitud.id)
      notificar('Borrador eliminado')
      onCambio()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setOcupado(null)
    }
  }

  async function aprobar(lineaId: string) {
    setAprobandoLinea(lineaId)
    setError(null)
    try {
      await api.solicitudesPrecios.aprobarLinea(solicitud.id, lineaId)
      notificar('Precio aprobado: el descompuesto de la partida se ha actualizado')
      onAprobado()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setAprobandoLinea(null)
    }
  }

  async function duplicarPara(proveedor: Tercero) {
    setError(null)
    try {
      await api.solicitudesPrecios.create({
        presupuesto_id: solicitud.presupuesto_id,
        proveedor_id: proveedor.id,
        partida_ids: solicitud.lineas
          .map((l) => l.partida_id)
          .filter((id): id is string => id != null),
        notas: notas || null,
      })
      notificar(`Borrador creado para ${proveedor.razon_social}`)
      setDuplicando(false)
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal
      title={`${solicitud.codigo} · ${solicitud.proveedor_razon_social}`}
      onClose={onClose}
    >
      <div className="form-section">
        <p className="muted" style={{ marginBottom: 'var(--sp-3)' }}>
          <span className={`chip chip--estado-${solicitud.estado}`}>
            {ETIQUETA_ESTADO_SOLICITUD[solicitud.estado] ?? solicitud.estado}
          </span>
          {solicitud.proveedor_email ? ` · ${solicitud.proveedor_email}` : ' · sin correo'}
          {solicitud.fecha_limite ? ` · fecha límite ${solicitud.fecha_limite}` : ''}
        </p>

        <ErrorNotice error={error} />

        {enlace && (
          <div className="notice" style={{ marginBottom: 'var(--sp-4)' }}>
            <p className="field__label">Enlace del proveedor</p>
            <input className="input" readOnly value={enlace} onFocus={(e) => e.target.select()} />
            <p className="muted" style={{ marginTop: 'var(--sp-1)' }}>
              Solo se puede ver ahora: en base de datos queda cifrado. Si lo pierdes habrá que
              generar otro, y este dejará de funcionar.
            </p>
          </div>
        )}

        {esBorrador ? (
          <>
            <p className="field__label">Partidas</p>
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

            <Field label="Notas para el proveedor (opcional)">
              <textarea
                className="input"
                rows={3}
                value={notas}
                onChange={(e) => setNotas(e.target.value)}
              />
            </Field>
          </>
        ) : (
          <>
            <p className="field__label">Partidas y precios recibidos</p>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Partida</th>
                    <th>Medición</th>
                    <th>Precio ofertado</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {solicitud.lineas.map((l) => (
                    <tr key={l.id}>
                      <td>
                        <span className="muted">{l.capitulo_resumen}</span>
                        <br />
                        {l.resumen}
                        {l.observaciones_proveedor && (
                          <div className="muted">{l.observaciones_proveedor}</div>
                        )}
                      </td>
                      <td className="table__num">
                        {l.medicion} {l.unidad}
                      </td>
                      <td className="table__num">
                        {l.precio_ofertado ? `${formatoImporte(l.precio_ofertado)} €` : '—'}
                      </td>
                      <td>
                        {l.aprobada ? (
                          <span className="badge badge--success">
                            <Check size={12} aria-hidden="true" /> Aprobada
                          </span>
                        ) : (
                          l.precio_ofertado && (
                            <Tooltip texto="Sustituye el descompuesto de la partida por esta subcontrata">
                              <button
                                className="btn btn--sm"
                                disabled={aprobandoLinea === l.id}
                                onClick={() => void aprobar(l.id)}
                              >
                                {aprobandoLinea === l.id ? 'Aprobando…' : 'Aprobar'}
                              </button>
                            </Tooltip>
                          )
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {solicitud.notas && (
              <>
                <p className="field__label" style={{ marginTop: 'var(--sp-4)' }}>
                  Notas enviadas
                </p>
                <p>{solicitud.notas}</p>
              </>
            )}
          </>
        )}

        <p className="field__label" style={{ marginTop: 'var(--sp-4)' }}>
          Documentos para el proveedor
        </p>
        <p className="form-section__note">
          Los ve y se los descarga desde su enlace, sin necesidad de cuenta.
        </p>
        <Documentos entidad="solicitud_precios" entidadId={solicitud.id} />

        <button
          className="btn btn--sm"
          style={{ marginTop: 'var(--sp-3)' }}
          onClick={() => setDuplicando(true)}
        >
          <Copy size={14} aria-hidden="true" />
          Pedir lo mismo a otro proveedor…
        </button>
      </div>

      <div className="form-actions">
        {esBorrador && (
          <button className="btn" onClick={() => void eliminar()} disabled={ocupado !== null}>
            <Trash2 size={16} aria-hidden="true" />
            {ocupado === 'eliminando' ? 'Eliminando…' : 'Eliminar'}
          </button>
        )}
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cerrar
        </button>
        {esBorrador && (
          <button className="btn" disabled={ocupado !== null} onClick={() => void guardar()}>
            {ocupado !== 'guardando' && <Save size={16} aria-hidden="true" />}
            {ocupado === 'guardando' ? 'Guardando…' : 'Guardar'}
          </button>
        )}
        <Tooltip
          texto={
            enlace
              ? 'Copiar el enlace recién emitido'
              : 'Genera el enlace para pasárselo tú (WhatsApp, tu propio correo…)'
          }
        >
          <button className="btn" disabled={ocupado !== null} onClick={() => void copiarEnlace()}>
            <Link2 size={16} aria-hidden="true" />
            {ocupado === 'enlace' ? 'Generando…' : 'Copiar enlace'}
          </button>
        </Tooltip>
        {esBorrador && (
          <Tooltip
            texto={
              solicitud.proveedor_email
                ? `Enviar a ${solicitud.proveedor_email}`
                : 'Este proveedor no tiene correo: usa «Copiar enlace»'
            }
          >
            <button
              className="btn btn--primary"
              disabled={ocupado !== null || !solicitud.proveedor_email}
              onClick={() => void enviarPorCorreo()}
            >
              {ocupado !== 'enviando' && <Mail size={16} aria-hidden="true" />}
              {ocupado === 'enviando' ? 'Enviando…' : 'Enviar por correo'}
            </button>
          </Tooltip>
        )}
      </div>

      {duplicando && (
        <SeleccionarProveedorModal
          onClose={() => setDuplicando(false)}
          onElegido={(p) => void duplicarPara(p)}
        />
      )}
    </Modal>
  )
}

/** Picker mínimo de proveedor, con alta al vuelo — para «Pedir lo mismo a
 *  otro proveedor», que crea una solicitud hermana en vez de meter varios
 *  proveedores en la misma (una solicitud sigue siendo de UN proveedor). */
function SeleccionarProveedorModal({
  onClose,
  onElegido,
}: {
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

  return (
    <Modal title="Elegir proveedor" onClose={onClose}>
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
              const proveedor = proveedores.find((p) => p.id === e.target.value)
              if (proveedor) onElegido(proveedor)
            }}
          >
            <option value="">Elige un proveedor…</option>
            {proveedores.map((p) => (
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
