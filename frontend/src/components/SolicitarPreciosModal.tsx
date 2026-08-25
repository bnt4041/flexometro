import { useEffect, useState } from 'react'
import { Save, X } from 'lucide-react'

import { CrearTerceroModal } from './CrearTerceroModal'
import { ErrorNotice, Field, Modal } from './ui'
import { api } from '../lib/api'
import type { Tercero } from '../lib/api'
import { useToast } from '../toast'

const NUEVO_PROVEEDOR = '__nuevo__'

interface FilaSolicitar {
  id: string
  resumen: string
  unidad: string
}

/** «Solicitar precios…» (Fase 53, revisado): crea un BORRADOR — no manda
 *  nada todavía. Se completa (partidas, más proveedores, notas, documentos)
 *  y se envía desde su ficha en la pestaña Comparativo (`SolicitudFicha`),
 *  donde vive el resto del ciclo de vida de la solicitud. */
export function SolicitarPreciosModal({
  presupuestoId,
  partidas,
  onClose,
  onCreada,
}: {
  presupuestoId: string
  partidas: FilaSolicitar[]
  onClose: () => void
  onCreada: () => void
}) {
  const { notificar } = useToast()
  const [proveedores, setProveedores] = useState<Tercero[]>([])
  const [proveedorId, setProveedorId] = useState('')
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

  async function guardar() {
    if (!proveedorId) return
    setGuardando(true)
    setError(null)
    try {
      await api.solicitudesPrecios.create({
        presupuesto_id: presupuestoId,
        proveedor_id: proveedorId,
        partida_ids: partidas.map((p) => p.id),
        fecha_limite: fechaLimite || null,
        notas: notas || null,
      })
      notificar(
        partidas.length === 1
          ? 'Borrador creado — complétalo en la pestaña Comparativo'
          : `Borrador creado (${partidas.length} partidas) — complétalo en la pestaña Comparativo`,
      )
      onCreada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal title="Solicitar precios a proveedor" onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          Crea un borrador con estas partidas. Desde la pestaña Comparativo se puede ajustar,
          añadir más proveedores a comparar, adjuntar documentos y, cuando esté listo, enviarlo.
        </p>

        <ErrorNotice error={error} />

        <Field label="Proveedor">
          <select
            className="select"
            value={proveedorId}
            onChange={(e) => {
              if (e.target.value === NUEVO_PROVEEDOR) {
                setCreandoProveedor(true)
                return
              }
              setProveedorId(e.target.value)
            }}
          >
            <option value="">Elige un proveedor…</option>
            {proveedores.map((p) => (
              <option key={p.id} value={p.id}>
                {p.razon_social}
              </option>
            ))}
            <option value={NUEVO_PROVEEDOR}>+ Nuevo proveedor…</option>
          </select>
        </Field>
        <Field label="Fecha límite (opcional)">
          <input
            className="input"
            type="date"
            value={fechaLimite}
            onChange={(e) => setFechaLimite(e.target.value)}
          />
        </Field>
        <Field label="Notas para el proveedor (opcional)">
          <textarea
            className="input"
            rows={3}
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
          />
        </Field>

        <p className="field__label">
          {partidas.length} partida{partidas.length === 1 ? '' : 's'}
        </p>
        <ul className="chat-ia__componentes">
          {partidas.map((p) => (
            <li key={p.id}>
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
          disabled={!proveedorId || guardando}
          onClick={() => void guardar()}
        >
          {!guardando && <Save size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : 'Guardar borrador'}
        </button>
      </div>

      {creandoProveedor && (
        <CrearTerceroModal
          rolPorDefecto="proveedor"
          onClose={() => setCreandoProveedor(false)}
          onCreado={(tercero) => {
            setProveedores((actual) => [...actual, tercero])
            setProveedorId(tercero.id)
            setCreandoProveedor(false)
          }}
        />
      )}
    </Modal>
  )
}
