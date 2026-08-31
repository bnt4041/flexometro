import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import { Plus, Search, Trash2, UserPlus } from 'lucide-react'

import { api } from '../lib/api'
import type { Contacto, FirmanteIn } from '../lib/api'

export type EditorFirmantesHandle = {
  /** Recoge lo que haya escrito y todavía sin añadir, y DEVUELVE la lista
   *  definitiva. `null` si hay algo escrito pero incompleto, para que quien
   *  envía se pare en vez de mandar el documento perdiéndolo.
   *
   *  Devuelve la lista en vez de un `boolean` porque `onCambio` actualiza
   *  estado del padre, y quien llama a esto lo hace justo antes de enviar:
   *  en ese momento su `useState` todavía tiene la lista ANTERIOR, así que
   *  leerla de allí mandaría el documento sin el firmante recién recogido. */
  confirmarPendiente: () => FirmanteIn[] | null
}

/** Quién tiene que firmar un documento.
 *
 *  Dos formas de añadir, porque son dos situaciones distintas: elegir de la
 *  agenda (lo habitual con alguien con quien ya se ha trabajado) o escribir
 *  nombre y correo a mano, con la opción de guardarlo como contacto para no
 *  tener que volver a teclearlo la próxima vez.
 *
 *  Ojo con lo escrito y no añadido: teclear un firmante y darle directamente
 *  a «Crear» sin pulsar «Añadir firmante» hacía que esa persona desapareciera
 *  sin decir nada, y el documento salía a firmar con uno menos. Por eso el
 *  componente expone `confirmarPendiente()`: quien envía lo llama antes y lo
 *  escrito se recoge solo. */
export const EditorFirmantes = forwardRef<
  EditorFirmantesHandle,
  {
    firmantes: FirmanteIn[]
    onCambio: (firmantes: FirmanteIn[]) => void
    /** Empresa a la que asociar los contactos que se den de alta desde aquí. */
    terceroId?: string | null
  }
>(function EditorFirmantes({ firmantes, onCambio, terceroId }, ref) {
  const [modo, setModo] = useState<'agenda' | 'manual'>('agenda')
  const [busqueda, setBusqueda] = useState('')
  const [resultados, setResultados] = useState<Contacto[]>([])
  const [buscando, setBuscando] = useState(false)
  const [nombre, setNombre] = useState('')
  const [email, setEmail] = useState('')
  const [telefono, setTelefono] = useState('')
  const [guardar, setGuardar] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const primeraCarga = useRef(true)

  useEffect(() => {
    // Carga inicial de la agenda para que el selector no salga vacío antes de
    // escribir nada.
    if (!primeraCarga.current) return
    primeraCarga.current = false
    api.contactos
      .list({ limit: 25 })
      .then((p) => setResultados(p.items))
      .catch(() => setResultados([]))
  }, [])

  async function buscar() {
    setBuscando(true)
    try {
      const pagina = await api.contactos.list({ q: busqueda || undefined, limit: 25 })
      setResultados(pagina.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBuscando(false)
    }
  }

  function yaEsta(email: string): boolean {
    return firmantes.some((f) => f.email.toLowerCase() === email.toLowerCase().trim())
  }

  function anadirDeAgenda(contacto: Contacto) {
    if (!contacto.email) {
      setError(`${contacto.nombre} no tiene correo en la agenda; añádeselo o escríbelo a mano.`)
      return
    }
    if (yaEsta(contacto.email)) {
      setError('Esa persona ya está en la lista.')
      return
    }
    setError(null)
    onCambio([
      ...firmantes,
      {
        nombre: [contacto.nombre, contacto.apellidos].filter(Boolean).join(' '),
        email: contacto.email,
        // Se prefiere el móvil: es a donde llega un WhatsApp, no a la
        // centralita de la oficina.
        telefono: contacto.movil || contacto.telefono || null,
        contacto_id: contacto.id,
      },
    ])
  }

  /** Devuelve la lista resultante, o `null` si lo escrito no vale. */
  function anadirManual(): FirmanteIn[] | null {
    if (!nombre.trim() || !email.trim()) {
      setError('Hacen falta el nombre y el correo.')
      return null
    }
    if (yaEsta(email)) {
      setError('Ese correo ya está en la lista.')
      return null
    }
    setError(null)
    const lista = [
      ...firmantes,
      {
        nombre: nombre.trim(),
        email: email.trim(),
        telefono: telefono.trim() || null,
        guardar_como_contacto: guardar,
        tercero_id: terceroId ?? null,
      },
    ]
    onCambio(lista)
    setNombre('')
    setEmail('')
    setTelefono('')
    return lista
  }

  /** Hay algo tecleado en el alta manual que todavía no está en la lista. */
  const hayPendiente = Boolean(nombre.trim() || email.trim() || telefono.trim())

  useImperativeHandle(
    ref,
    () => ({
      confirmarPendiente: () => (hayPendiente ? anadirManual() : firmantes),
    }),
    // `anadirManual` se recrea en cada render y lee el estado de ese render,
    // que es justo lo que hace falta: se quiere lo escrito AHORA.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hayPendiente, nombre, email, telefono, firmantes],
  )

  return (
    <div>
      {firmantes.length > 0 && (
        <div style={{ marginBottom: 'var(--sp-3)' }}>
          <table className="table">
            <tbody>
              {firmantes.map((firmante, indice) => (
                <tr key={`${firmante.email}-${indice}`}>
                  <td style={{ width: 28, color: 'var(--c-text-muted)' }}>{indice + 1}</td>
                  <td>
                    {firmante.nombre}
                    <div className="muted" style={{ fontSize: '0.85em' }}>
                      {firmante.email}
                      {firmante.telefono ? ` · ${firmante.telefono}` : ''}
                      {firmante.contacto_id
                        ? ' · de la agenda'
                        : firmante.guardar_como_contacto
                          ? ' · se guardará como contacto'
                          : ''}
                    </div>
                    <div
                      className="muted"
                      style={{ fontSize: '0.8em', marginTop: 2 }}
                    >
                      {firmante.telefono
                        ? 'Enlace por WhatsApp · código por correo'
                        : 'Enlace y código por correo'}
                    </div>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button
                      type="button"
                      className="btn btn--sm btn--danger"
                      onClick={() => onCambio(firmantes.filter((_, i) => i !== indice))}
                      aria-label={`Quitar a ${firmante.nombre}`}
                    >
                      <Trash2 size={13} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {error && <p className="notice notice--error">{error}</p>}

      {hayPendiente && (
        <p className="notice" style={{ fontSize: '0.9em' }}>
          Tienes un firmante escrito sin añadir. Pulsa <strong>Añadir firmante</strong> —
          si no, se añadirá solo al guardar.
        </p>
      )}

      <div style={{ display: 'flex', gap: 'var(--sp-2)', marginBottom: 'var(--sp-2)' }}>
        <button
          type="button"
          className={`btn btn--sm${modo === 'agenda' ? ' btn--primary' : ''}`}
          onClick={() => setModo('agenda')}
        >
          <Search size={14} aria-hidden="true" /> De la agenda
        </button>
        <button
          type="button"
          className={`btn btn--sm${modo === 'manual' ? ' btn--primary' : ''}`}
          onClick={() => setModo('manual')}
        >
          <UserPlus size={14} aria-hidden="true" /> Escribir a mano
        </button>
      </div>

      {modo === 'agenda' ? (
        <div>
          <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
            <input
              className="input"
              value={busqueda}
              placeholder="Buscar en contactos…"
              onChange={(e) => setBusqueda(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  void buscar()
                }
              }}
            />
            <button type="button" className="btn" onClick={() => void buscar()} disabled={buscando}>
              {buscando ? 'Buscando…' : 'Buscar'}
            </button>
          </div>
          <div
            style={{
              maxHeight: 170,
              overflowY: 'auto',
              marginTop: 'var(--sp-2)',
              border: '1px solid var(--c-border)',
              borderRadius: 'var(--radius)',
            }}
          >
            {resultados.length === 0 ? (
              <p className="muted" style={{ margin: 'var(--sp-3)' }}>
                Sin contactos. Puedes escribir el firmante a mano.
              </p>
            ) : (
              <table className="table">
                <tbody>
                  {resultados.map((contacto) => (
                    <tr
                      key={contacto.id}
                      onClick={() => anadirDeAgenda(contacto)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td>
                        {contacto.nombre} {contacto.apellidos ?? ''}
                        <div className="muted" style={{ fontSize: '0.85em' }}>
                          {contacto.email || 'Sin correo'}
                          {contacto.cargo ? ` · ${contacto.cargo}` : ''}
                        </div>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <Plus size={14} aria-hidden="true" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      ) : (
        <div className="form-grid">
          <div className="field">
            <span className="field__label">Nombre</span>
            <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </div>
          <div className="field">
            <span className="field__label">Correo</span>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  anadirManual()
                }
              }}
            />
          </div>
          <div className="field field--doble">
            <span className="field__label">Móvil (opcional)</span>
            <input
              className="input"
              type="tel"
              value={telefono}
              placeholder="+34 600 11 22 33"
              onChange={(e) => setTelefono(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  anadirManual()
                }
              }}
            />
            <p className="muted" style={{ fontSize: '0.85em', margin: 'var(--sp-1) 0 0' }}>
              Con móvil, el enlace le llega por WhatsApp y el código de
              verificación por correo. Que vayan por sitios distintos es lo que
              hace que el segundo factor sirva de algo.
            </p>
          </div>
          <div className="field field--doble">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={guardar}
                onChange={(e) => setGuardar(e.target.checked)}
              />
              <span>Guardar también como contacto en la agenda</span>
            </label>
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => anadirManual()}
              style={{ marginTop: 'var(--sp-2)' }}
            >
              <Plus size={14} aria-hidden="true" /> Añadir firmante
            </button>
          </div>
        </div>
      )}
    </div>
  )
})
