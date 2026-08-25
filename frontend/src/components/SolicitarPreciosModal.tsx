import { useEffect, useState } from 'react'
import { Save, X } from 'lucide-react'

import { CrearTerceroModal } from './CrearTerceroModal'
import { Checkbox, ErrorNotice, Field, Modal } from './ui'
import { api } from '../lib/api'
import type { ComponentePedido, Tercero } from '../lib/api'
import { useToast } from '../toast'

/** Lo que se le enseña al usuario de la selección que trae, sea de partidas
 *  enteras o de componentes sueltos de un descompuesto. */
export interface ItemSolicitado {
  clave: string
  resumen: string
  unidad: string
}

/** «Solicitar precios…»: crea un PAQUETE de trabajo con nombre ("Yeserías")
 *  sobre las partidas seleccionadas, y lo deja en borrador.
 *
 *  No manda nada todavía: se completa y se envía proveedor a proveedor desde
 *  su ficha en la pestaña Comparativo, que es donde vive el resto del ciclo
 *  de vida. */
export function SolicitarPreciosModal({
  presupuestoId,
  items,
  seleccion,
  onClose,
  onCreada,
}: {
  presupuestoId: string
  /** Solo para enseñar qué se está pidiendo. */
  items: ItemSolicitado[]
  /** Lo que de verdad se manda al backend. */
  seleccion: { partida_ids?: string[]; componentes?: ComponentePedido[] }
  onClose: () => void
  onCreada: () => void
}) {
  const { notificar } = useToast()
  const [titulo, setTitulo] = useState('')
  const [proveedores, setProveedores] = useState<Tercero[]>([])
  const [elegidos, setElegidos] = useState<Set<string>>(new Set())
  const [creandoProveedor, setCreandoProveedor] = useState(false)
  const [fechaLimite, setFechaLimite] = useState('')
  const [notas, setNotas] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    void api.terceros
      .list({ rol: 'proveedor', activo: true, limit: 500 })
      .then((pagina) => setProveedores(pagina.items))
  }, [])

  function alternar(id: string) {
    setElegidos((actual) => {
      const nueva = new Set(actual)
      if (nueva.has(id)) nueva.delete(id)
      else nueva.add(id)
      return nueva
    })
  }

  async function guardar() {
    if (!titulo.trim()) {
      setError('Ponle un nombre al paquete, por ejemplo «Yeserías»')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      await api.solicitudesPrecios.create({
        presupuesto_id: presupuestoId,
        titulo: titulo.trim(),
        proveedor_ids: [...elegidos],
        ...seleccion,
        fecha_limite: fechaLimite || null,
        notas: notas || null,
      })
      notificar(`«${titulo.trim()}» creada — complétala en la pestaña Comparativo`)
      onCreada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal title="Nueva solicitud de precios" onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          Se crea un paquete de trabajo con estas partidas. Puedes mandárselo a varios
          proveedores y comparar sus ofertas; se envía desde la pestaña Comparativo.
        </p>

        <ErrorNotice error={error} />

        <Field label="Nombre" hint="Cómo lo vas a reconocer: «Yeserías», «Instalación eléctrica»…">
          <input
            className="input"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Yeserías"
            autoFocus
          />
        </Field>

        <p className="field__label">Proveedores a los que pedírselo</p>
        <p className="form-section__note">Se pueden añadir más después, desde la ficha.</p>
        {proveedores.map((p) => (
          <Checkbox
            key={p.id}
            label={p.razon_social + (p.email ? '' : ' (sin correo)')}
            checked={elegidos.has(p.id)}
            onChange={() => alternar(p.id)}
          />
        ))}
        <button
          className="btn btn--sm"
          style={{ marginTop: 'var(--sp-2)' }}
          onClick={() => setCreandoProveedor(true)}
        >
          + Nuevo proveedor…
        </button>

        <Field label="Fecha límite (opcional)">
          <input
            className="input"
            type="date"
            value={fechaLimite}
            onChange={(e) => setFechaLimite(e.target.value)}
          />
        </Field>
        <Field label="Notas para los proveedores (opcional)">
          <textarea
            className="input"
            rows={3}
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
          />
        </Field>

        <p className="field__label">
          Se pide precio de {items.length} {items.length === 1 ? 'línea' : 'líneas'}
        </p>
        <ul className="chat-ia__componentes">
          {items.map((p) => (
            <li key={p.clave}>
              {p.resumen} ({p.unidad})
            </li>
          ))}
        </ul>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={!titulo.trim() || guardando}
          onClick={() => void guardar()}
        >
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? 'Creando…' : 'Crear solicitud'}
        </button>
      </div>

      {creandoProveedor && (
        <CrearTerceroModal
          rolPorDefecto="proveedor"
          onClose={() => setCreandoProveedor(false)}
          onCreado={(tercero) => {
            setProveedores((actual) => [...actual, tercero])
            setElegidos((actual) => new Set(actual).add(tercero.id))
            setCreandoProveedor(false)
          }}
        />
      )}
    </Modal>
  )
}
