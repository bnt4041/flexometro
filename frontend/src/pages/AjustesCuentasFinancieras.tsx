import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Banknote, Plus, Save, Trash2, Wallet, X } from 'lucide-react'

import { Checkbox, EmptyState, ErrorNotice, Field, Modal } from '../components/ui'
import { api } from '../lib/api'
import type { CuentaFinanciera, CuentaFinancieraCreate, TipoCuentaFinanciera } from '../lib/api'
import { useToast } from '../toast'

const VACIA: CuentaFinancieraCreate = {
  nombre: '',
  tipo: 'banco',
  banco: '',
  iban: '',
  bic: '',
  es_predeterminada: false,
  activa: true,
  notas: '',
}

/** Bancos y cajas de la empresa activa (Fase 44) — dónde está el dinero.
 *  La cuenta marcada como predeterminada sale ya elegida al registrar un
 *  cobro y es la que imprimen las plantillas de exportación
 *  (`banco.iban`, `banco.entidad`…). */
export function AjustesCuentasFinancieras() {
  const { notificar } = useToast()
  const [cuentas, setCuentas] = useState<CuentaFinanciera[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editando, setEditando] = useState<CuentaFinanciera | 'nueva' | null>(null)

  const cargar = useCallback(async () => {
    try {
      setCuentas(await api.ajustes.cuentasFinancieras.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function eliminar(cuenta: CuentaFinanciera) {
    if (!window.confirm(`¿Eliminar «${cuenta.nombre}»? No se puede deshacer.`)) return
    try {
      await api.ajustes.cuentasFinancieras.remove(cuenta.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Bancos y cajas</h1>
          <p className="page-lead">
            Dónde entra y de dónde sale el dinero de esta empresa. La cuenta predeterminada sale ya
            elegida al registrar un cobro, y es la que imprimen las plantillas de exportación
            (<code>banco.iban</code>, <code>banco.entidad</code>…).
          </p>
        </div>
        <Link className="btn" to="/ajustes">
          <ArrowLeft size={16} aria-hidden="true" />
          Volver a Ajustes
        </Link>
      </div>

      <ErrorNotice error={error} />

      <div className="toolbar">
        <button className="btn btn--primary" onClick={() => setEditando('nueva')}>
          <Plus size={16} aria-hidden="true" />
          Nueva cuenta
        </button>
      </div>

      {cuentas.length === 0 ? (
        <EmptyState title="Sin bancos ni cajas todavía">
          Da de alta la cuenta del banco por la que cobras y, si la usas, la caja de efectivo.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Tipo</th>
                <th>Entidad</th>
                <th>IBAN</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {cuentas.map((c) => (
                <tr key={c.id} style={c.activa ? undefined : { opacity: 0.55 }}>
                  <td>
                    {c.nombre}
                    {c.es_predeterminada && (
                      <span className="badge badge--info" style={{ marginLeft: 'var(--sp-2)' }}>
                        Predeterminada
                      </span>
                    )}
                    {!c.activa && (
                      <span className="badge" style={{ marginLeft: 'var(--sp-2)' }}>
                        Desactivada
                      </span>
                    )}
                  </td>
                  <td>
                    {c.tipo === 'banco' ? (
                      <>
                        <Banknote size={14} aria-hidden="true" /> Banco
                      </>
                    ) : (
                      <>
                        <Wallet size={14} aria-hidden="true" /> Caja
                      </>
                    )}
                  </td>
                  <td className="muted">{c.banco || '—'}</td>
                  <td className="table__code">{c.iban || '—'}</td>
                  <td style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                    <button className="btn btn--sm" onClick={() => setEditando(c)}>
                      Editar
                    </button>
                    <button className="btn btn--sm btn--danger" onClick={() => void eliminar(c)}>
                      <Trash2 size={14} aria-hidden="true" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editando && (
        <CuentaModal
          cuenta={editando === 'nueva' ? null : editando}
          onClose={() => setEditando(null)}
          onGuardada={async (mensaje) => {
            setEditando(null)
            await cargar()
            notificar(mensaje)
          }}
        />
      )}
    </>
  )
}

function CuentaModal({
  cuenta,
  onClose,
  onGuardada,
}: {
  cuenta: CuentaFinanciera | null
  onClose: () => void
  onGuardada: (mensaje: string) => Promise<void>
}) {
  const [datos, setDatos] = useState<CuentaFinancieraCreate>(
    cuenta
      ? {
          nombre: cuenta.nombre,
          tipo: cuenta.tipo,
          banco: cuenta.banco ?? '',
          iban: cuenta.iban ?? '',
          bic: cuenta.bic ?? '',
          es_predeterminada: cuenta.es_predeterminada,
          activa: cuenta.activa,
          notas: cuenta.notas ?? '',
        }
      : VACIA,
  )
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  const esCaja = datos.tipo === 'caja'
  const campo = <K extends keyof CuentaFinancieraCreate>(clave: K, valor: CuentaFinancieraCreate[K]) =>
    setDatos((d) => ({ ...d, [clave]: valor }))

  async function guardar() {
    if (!datos.nombre.trim()) {
      setError('El nombre es obligatorio')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      // Una caja no lleva datos de banco: se limpian antes de enviar en vez
      // de dejar restos si el usuario cambió el tipo después de escribirlos
      // (el backend los rechaza).
      const cuerpo: CuentaFinancieraCreate = {
        ...datos,
        nombre: datos.nombre.trim(),
        banco: esCaja ? null : datos.banco || null,
        iban: esCaja ? null : datos.iban || null,
        bic: esCaja ? null : datos.bic || null,
        notas: datos.notas || null,
      }
      if (cuenta) await api.ajustes.cuentasFinancieras.update(cuenta.id, cuerpo)
      else await api.ajustes.cuentasFinancieras.create(cuerpo)
      await onGuardada(cuenta ? 'Cuenta actualizada' : 'Cuenta creada')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal title={cuenta ? 'Editar cuenta' : 'Nueva cuenta'} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="form-grid">
          <Field ancho="doble" label="Nombre" hint="Cómo la reconoces tú: «Santander principal», «Caja de obra»…">
            <input
              className="input"
              value={datos.nombre}
              onChange={(e) => campo('nombre', e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Tipo">
            <select
              className="select"
              value={datos.tipo}
              onChange={(e) => campo('tipo', e.target.value as TipoCuentaFinanciera)}
            >
              <option value="banco">Banco</option>
              <option value="caja">Caja de efectivo</option>
            </select>
          </Field>
        </div>

        {!esCaja && (
          <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
            <Field ancho="doble" label="Entidad">
              <input
                className="input"
                value={datos.banco ?? ''}
                onChange={(e) => campo('banco', e.target.value)}
              />
            </Field>
            <Field ancho="doble" label="IBAN">
              <input
                className="input"
                value={datos.iban ?? ''}
                onChange={(e) => campo('iban', e.target.value)}
              />
            </Field>
            <Field label="BIC / SWIFT">
              <input
                className="input"
                value={datos.bic ?? ''}
                onChange={(e) => campo('bic', e.target.value)}
              />
            </Field>
          </div>
        )}

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
            label="Predeterminada"
            checked={datos.es_predeterminada ?? false}
            onChange={(v) => campo('es_predeterminada', v)}
          />
          <Checkbox
            label="Activa"
            checked={datos.activa ?? true}
            onChange={(v) => campo('activa', v)}
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
