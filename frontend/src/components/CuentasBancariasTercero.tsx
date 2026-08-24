import { useCallback, useEffect, useState } from 'react'
import { Plus, Save, Star, Trash2, X } from 'lucide-react'

import { Checkbox, EmptyState, ErrorNotice, Field, Modal, Tooltip } from './ui'
import { api } from '../lib/api'
import type { CuentaBancariaTercero, CuentaBancariaTerceroCreate } from '../lib/api'

const VACIA: CuentaBancariaTerceroCreate = {
  tercero_id: '',
  titular: '',
  iban: '',
  bic: '',
  es_principal: false,
  notas: '',
  activo: true,
}

/** Pestaña "Cuentas bancarias" (Fase 47) de la ficha de un tercero: los IBAN
 *  que el cliente o proveedor nos ha dado — para saber a qué cuenta pagarle
 *  o de cuál se le gira el recibo. Distinto de Ajustes -> Bancos y cajas,
 *  que son las cuentas PROPIAS de la empresa. */
export function CuentasBancariasTercero({ terceroId }: { terceroId: string }) {
  const [cuentas, setCuentas] = useState<CuentaBancariaTercero[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [editando, setEditando] = useState<CuentaBancariaTercero | 'nueva' | null>(null)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      setCuentas(await api.terceros.cuentasBancarias.list(terceroId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [terceroId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function eliminar(cuenta: CuentaBancariaTercero) {
    if (!window.confirm(`¿Eliminar la cuenta ${cuenta.iban}? No se puede deshacer.`)) return
    try {
      await api.terceros.cuentasBancarias.remove(terceroId, cuenta.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  if (cargando) return null

  return (
    <>
      <div className="page-head">
        <p className="page-lead" style={{ marginBottom: 0 }}>
          IBAN que este tercero nos ha dado, para pagarle o para domiciliarle un cobro.
        </p>
        <Tooltip texto="Añadir una cuenta bancaria">
          <button className="btn" onClick={() => setEditando('nueva')}>
            <Plus size={16} aria-hidden="true" />
            Añadir cuenta
          </button>
        </Tooltip>
      </div>

      <ErrorNotice error={error} />

      {cuentas.length === 0 ? (
        <EmptyState title="Sin cuentas bancarias todavía">
          Añade el IBAN de este tercero en cuanto lo necesites para un pago o una domiciliación.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Titular</th>
                <th>IBAN</th>
                <th>BIC</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {cuentas.map((c) => (
                <tr key={c.id} style={c.activo ? undefined : { opacity: 0.55 }}>
                  <td>
                    {c.titular || <span className="muted">—</span>}
                    {c.es_principal && (
                      <Tooltip texto="Cuenta principal">
                        <Star size={14} aria-hidden="true" style={{ marginLeft: 'var(--sp-2)' }} />
                      </Tooltip>
                    )}
                    {!c.activo && (
                      <span className="badge" style={{ marginLeft: 'var(--sp-2)' }}>
                        Desactivada
                      </span>
                    )}
                  </td>
                  <td className="table__code">{c.iban}</td>
                  <td className="muted">{c.bic || '—'}</td>
                  <td className="table__actions">
                    <Tooltip texto="Editar">
                      <button className="btn btn--sm" onClick={() => setEditando(c)}>
                        Editar
                      </button>
                    </Tooltip>
                    <Tooltip texto="Eliminar">
                      <button
                        className="btn btn--sm btn--danger btn--solo-icono"
                        onClick={() => void eliminar(c)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </Tooltip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editando && (
        <CuentaBancariaModal
          terceroId={terceroId}
          cuenta={editando === 'nueva' ? null : editando}
          onClose={() => setEditando(null)}
          onGuardada={async () => {
            setEditando(null)
            await cargar()
          }}
        />
      )}
    </>
  )
}

function CuentaBancariaModal({
  terceroId,
  cuenta,
  onClose,
  onGuardada,
}: {
  terceroId: string
  cuenta: CuentaBancariaTercero | null
  onClose: () => void
  onGuardada: () => Promise<void>
}) {
  const [datos, setDatos] = useState<CuentaBancariaTerceroCreate>(
    cuenta
      ? {
          tercero_id: terceroId,
          titular: cuenta.titular ?? '',
          iban: cuenta.iban,
          bic: cuenta.bic ?? '',
          es_principal: cuenta.es_principal,
          notas: cuenta.notas ?? '',
          activo: cuenta.activo,
        }
      : { ...VACIA, tercero_id: terceroId },
  )
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const campo = <K extends keyof CuentaBancariaTerceroCreate>(
    clave: K,
    valor: CuentaBancariaTerceroCreate[K],
  ) => setDatos((d) => ({ ...d, [clave]: valor }))

  async function guardar() {
    if (!datos.iban.trim()) {
      setError('El IBAN es obligatorio')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      const cuerpo: CuentaBancariaTerceroCreate = {
        ...datos,
        iban: datos.iban.trim(),
        titular: datos.titular || null,
        bic: datos.bic || null,
        notas: datos.notas || null,
      }
      if (cuenta) await api.terceros.cuentasBancarias.update(terceroId, cuenta.id, cuerpo)
      else await api.terceros.cuentasBancarias.create(terceroId, cuerpo)
      await onGuardada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal title={cuenta ? 'Editar cuenta bancaria' : 'Nueva cuenta bancaria'} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field ancho="doble" label="Titular" hint="Si es distinto del propio tercero">
            <input
              className="input"
              value={datos.titular ?? ''}
              onChange={(e) => campo('titular', e.target.value)}
              autoFocus
            />
          </Field>
          <Field ancho="doble" label="IBAN">
            <input className="input" value={datos.iban} onChange={(e) => campo('iban', e.target.value)} />
          </Field>
          <Field label="BIC / SWIFT">
            <input className="input" value={datos.bic ?? ''} onChange={(e) => campo('bic', e.target.value)} />
          </Field>
        </div>

        <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
          <Field ancho="completo" label="Notas">
            <textarea
              className="input"
              rows={2}
              value={datos.notas ?? ''}
              onChange={(e) => campo('notas', e.target.value)}
            />
          </Field>
        </div>

        <div style={{ display: 'flex', gap: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
          <Checkbox
            label="Cuenta principal"
            checked={datos.es_principal ?? false}
            onChange={(v) => campo('es_principal', v)}
          />
          <Checkbox
            label="Activa"
            checked={datos.activo ?? true}
            onChange={(v) => campo('activo', v)}
          />
        </div>
      </div>

      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          <Save size={16} aria-hidden="true" />
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </Modal>
  )
}
