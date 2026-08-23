import { useEffect, useState } from 'react'
import { Copy, X } from 'lucide-react'

import { Checkbox, ErrorNotice, Field, Modal } from './ui'
import { api } from '../lib/api'
import type { EmpresaAccesible, Tercero } from '../lib/api'

/** Copiar un presupuesto (Fase 45), aquí mismo o a otra empresa de la misma
 *  cuenta. Copiar y no mover es lo que lo hace seguro: el original se queda
 *  intacto, la copia nace en borrador y con la numeración de la empresa de
 *  destino, y nada queda apuntando a través de la frontera entre empresas. */
export function CopiarPresupuestoModal({
  presupuestoId,
  nombreActual,
  clienteIdActual,
  onClose,
  onCopiado,
}: {
  presupuestoId: string
  nombreActual: string
  clienteIdActual: string | null
  onClose: () => void
  onCopiado: (nuevoId: string, enOtraEmpresa: boolean) => void
}) {
  const [nombre, setNombre] = useState(`${nombreActual} (copia)`)
  const [empresas, setEmpresas] = useState<EmpresaAccesible[]>([])
  const [empresaId, setEmpresaId] = useState('')
  const [clientes, setClientes] = useState<Tercero[]>([])
  const [clienteId, setClienteId] = useState(clienteIdActual ?? '')
  const [conMediciones, setConMediciones] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copiando, setCopiando] = useState(false)

  useEffect(() => {
    void api
      .empresasAccesibles()
      .then((lista) => {
        setEmpresas(lista)
        setEmpresaId(lista.find((e) => e.es_la_actual)?.id ?? '')
      })
      .catch(() => setEmpresas([]))
  }, [])

  useEffect(() => {
    void api.terceros
      .list({ rol: 'cliente', limit: 500 })
      .then((p) => setClientes(p.items))
      .catch(() => setClientes([]))
  }, [])

  const otraEmpresa = empresas.find((e) => e.id === empresaId)?.es_la_actual === false

  async function copiar() {
    if (!nombre.trim()) {
      setError('Ponle un nombre a la copia')
      return
    }
    setCopiando(true)
    setError(null)
    try {
      const copia = await api.presupuestos.copiar(presupuestoId, {
        nombre: nombre.trim(),
        organization_id: empresaId || null,
        // Al cambiar de empresa el cliente sigue siendo válido solo si el
        // banco de maestros está compartido en la cuenta; si el usuario lo
        // deja vacío, la copia nace sin cliente y se elige allí.
        cliente_id: clienteId || null,
        con_mediciones: conMediciones,
      })
      onCopiado(copia.id, otraEmpresa)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCopiando(false)
    }
  }

  return (
    <Modal title="Copiar presupuesto" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          Se crea un presupuesto nuevo en borrador con la misma estructura. El original no se toca.
        </p>
        <div className="form-grid">
          <Field ancho="doble" label="Nombre de la copia">
            <input
              className="input"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              autoFocus
            />
          </Field>
          {empresas.length > 1 && (
            <Field label="Empresa" hint="Se numera con la serie de la empresa elegida">
              <select
                className="select"
                value={empresaId}
                onChange={(e) => setEmpresaId(e.target.value)}
              >
                {empresas.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                    {e.es_la_actual ? ' (actual)' : ''}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <Field ancho="doble" label="Cliente">
            <select
              className="select"
              value={clienteId}
              onChange={(e) => setClienteId(e.target.value)}
            >
              <option value="">Sin cliente</option>
              {clientes.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.razon_social}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Checkbox
            label="Copiar también las mediciones"
            checked={conMediciones}
            onChange={setConMediciones}
          />
        </div>

        {otraEmpresa && (
          <p className="form-section__note" style={{ marginTop: 'var(--sp-3)', marginBottom: 0 }}>
            La copia quedará en otra empresa, así que no la verás hasta que cambies a ella con el
            selector de la barra superior.
          </p>
        )}
      </div>

      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={copiando} onClick={() => void copiar()}>
          <Copy size={16} aria-hidden="true" />
          {copiando ? 'Copiando…' : 'Copiar'}
        </button>
      </div>
    </Modal>
  )
}
