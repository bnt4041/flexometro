import { useState } from 'react'
import { Plus, X } from 'lucide-react'

import { Checkbox, ErrorNotice, Field, Modal } from './ui'
import { api } from '../lib/api'
import type { Tercero } from '../lib/api'

/** Alta rápida de tercero desde dentro de otro formulario (elegir cliente al
 *  crear un presupuesto, por ejemplo) — mismos campos mínimos que
 *  `TerceroCrear` (Terceros.tsx), pero como modal anidado en vez de pantalla
 *  completa, para no perder lo que ya se llevaba rellenado en el formulario
 *  que lo abrió. `rolPorDefecto` marca el checkbox correspondiente, editable
 *  igualmente por si hace falta más de un rol. */
export function CrearTerceroModal({
  rolPorDefecto,
  onClose,
  onCreado,
}: {
  rolPorDefecto: 'cliente' | 'proveedor' | 'subcontratista'
  onClose: () => void
  onCreado: (tercero: Tercero) => void
}) {
  const [razonSocial, setRazonSocial] = useState('')
  const [nif, setNif] = useState('')
  const [ciudad, setCiudad] = useState('')
  const [email, setEmail] = useState('')
  const [esCliente, setEsCliente] = useState(rolPorDefecto === 'cliente')
  const [esProveedor, setEsProveedor] = useState(rolPorDefecto === 'proveedor')
  const [esSubcontratista, setEsSubcontratista] = useState(rolPorDefecto === 'subcontratista')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const tercero = await api.terceros.create({
        razon_social: razonSocial,
        nif: nif || null,
        es_cliente: esCliente,
        es_proveedor: esProveedor,
        es_subcontratista: esSubcontratista,
        ciudad: ciudad || null,
        email: email || null,
      })
      onCreado(tercero)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title="Nuevo tercero" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field ancho="doble" label="Razón social">
            <input
              className="input"
              value={razonSocial}
              onChange={(e) => setRazonSocial(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="NIF / CIF" hint="Opcional, se puede completar después">
            <input className="input" value={nif} onChange={(e) => setNif(e.target.value)} />
          </Field>
          <Field label="Población">
            <input className="input" value={ciudad} onChange={(e) => setCiudad(e.target.value)} />
          </Field>
          <Field
            ancho="doble"
            label="Email"
            hint="Para poder mandarle solicitudes de precios o documentos"
          >
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
        </div>
        <div style={{ display: 'flex', gap: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
          <Checkbox label="Cliente" checked={esCliente} onChange={setEsCliente} />
          <Checkbox label="Proveedor" checked={esProveedor} onChange={setEsProveedor} />
          <Checkbox label="Subcontratista" checked={esSubcontratista} onChange={setEsSubcontratista} />
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={guardando || razonSocial.trim() === ''}
          onClick={() => void guardar()}
        >
          <Plus size={16} aria-hidden="true" />
          {guardando ? 'Creando…' : 'Crear'}
        </button>
      </div>
    </Modal>
  )
}
