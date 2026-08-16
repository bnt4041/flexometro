import { useCallback, useEffect, useState } from 'react'
import { Plus, Power, Trash2 } from 'lucide-react'

import { ErrorNotice, Field, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { Descuento, MotivoDescuento, TipoDescuento } from '../lib/api'

export const ETIQUETA_TIPO: Record<TipoDescuento, string> = {
  porcentaje: 'Porcentaje',
  importe_fijo: 'Importe fijo',
}

export const ETIQUETA_MOTIVO: Record<MotivoDescuento, string> = {
  primer_mes_gratis: 'Primer mes gratis',
  fidelizacion: 'Fidelización',
  retencion: 'Retención',
  campana: 'Campaña',
  aumento_modulos: 'Aumento de módulos',
  otro: 'Otro',
}

/** Catálogo de descuentos de una tarifa: crear, editar y dar de baja. Se
 *  crean SOLO aquí — para aplicarlos a una organización concreta (y ver su
 *  histórico de aplicación/anulación) está `AplicacionesDescuentoCard`, en la
 *  ficha de esa organización. */
export function DescuentosCard({ tarifaId }: { tarifaId: string }) {
  const [items, setItems] = useState<Descuento[]>([])
  const [nombre, setNombre] = useState('')
  const [motivo, setMotivo] = useState<MotivoDescuento>('otro')
  const [tipo, setTipo] = useState<TipoDescuento>('porcentaje')
  const [valor, setValor] = useState('')
  const [vigenteDesde, setVigenteDesde] = useState('')
  const [vigenteHasta, setVigenteHasta] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      setItems(await api.admin.descuentos.list({ tarifa_id: tarifaId }))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [tarifaId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function crear() {
    setGuardando(true)
    setError(null)
    try {
      await api.admin.descuentos.create({
        tarifa_id: tarifaId,
        nombre,
        motivo,
        tipo,
        valor,
        vigente_desde: vigenteDesde || null,
        vigente_hasta: vigenteHasta || null,
      })
      setNombre('')
      setMotivo('otro')
      setValor('')
      setVigenteDesde('')
      setVigenteHasta('')
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function toggleActivo(descuento: Descuento) {
    setBusyId(descuento.id)
    try {
      await api.admin.descuentos.update(descuento.id, { activo: !descuento.activo })
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusyId(null)
    }
  }

  async function eliminar(descuento: Descuento) {
    if (!window.confirm(`¿Eliminar el descuento «${descuento.nombre}»?`)) return
    setBusyId(descuento.id)
    try {
      await api.admin.descuentos.remove(descuento.id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="card" style={{ padding: 'var(--sp-5)' }}>
      <ErrorNotice error={error} />
      <div className="form-grid">
        <Field label="Nombre">
          <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
        </Field>
        <Field label="Motivo">
          <select
            className="select"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value as MotivoDescuento)}
          >
            {(Object.entries(ETIQUETA_MOTIVO) as [MotivoDescuento, string][]).map(
              ([valor, etiqueta]) => (
                <option key={valor} value={valor}>
                  {etiqueta}
                </option>
              ),
            )}
          </select>
        </Field>
        <Field label="Tipo">
          <select
            className="select"
            value={tipo}
            onChange={(e) => setTipo(e.target.value as TipoDescuento)}
          >
            <option value="porcentaje">Porcentaje</option>
            <option value="importe_fijo">Importe fijo</option>
          </select>
        </Field>
        <Field label={tipo === 'porcentaje' ? 'Valor (%)' : 'Valor (€)'}>
          <input className="input" value={valor} onChange={(e) => setValor(e.target.value)} />
        </Field>
        <Field label="Vigente desde" hint="Opcional">
          <input
            className="input"
            type="date"
            value={vigenteDesde}
            onChange={(e) => setVigenteDesde(e.target.value)}
          />
        </Field>
        <Field label="Vigente hasta" hint="Opcional">
          <input
            className="input"
            type="date"
            value={vigenteHasta}
            onChange={(e) => setVigenteHasta(e.target.value)}
          />
        </Field>
      </div>
      <div className="form-actions">
        <button
          className="btn btn--primary"
          disabled={guardando || nombre.trim() === '' || valor.trim() === ''}
          onClick={() => void crear()}
        >
          {!guardando && <Plus size={16} aria-hidden="true" />}
          {guardando ? 'Creando…' : 'Añadir descuento'}
        </button>
      </div>

      <div className="table-wrap" style={{ marginTop: 'var(--sp-3)' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Motivo</th>
              <th>Tipo</th>
              <th className="table__num">Valor</th>
              <th>Vigencia</th>
              <th>Estado</th>
              <th className="table__actions" />
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id}>
                <td>{d.nombre}</td>
                <td className="muted">{ETIQUETA_MOTIVO[d.motivo]}</td>
                <td className="muted">{ETIQUETA_TIPO[d.tipo]}</td>
                <td className="table__num">
                  {formatoImporte(d.valor)} {d.tipo === 'porcentaje' ? '%' : '€'}
                </td>
                <td className="muted">
                  {d.vigente_desde || d.vigente_hasta
                    ? `${d.vigente_desde ?? '…'} → ${d.vigente_hasta ?? '…'}`
                    : 'Indefinida'}
                </td>
                <td>
                  <span className={`chip ${d.activo ? 'chip--proveedor' : 'chip--inactivo'}`}>
                    {d.activo ? 'activo' : 'inactivo'}
                  </span>
                </td>
                <td className="table__actions">
                  <button
                    className="btn btn--sm"
                    disabled={busyId === d.id}
                    onClick={() => void toggleActivo(d)}
                  >
                    <Power size={14} aria-hidden="true" />
                    {d.activo ? 'Desactivar' : 'Activar'}
                  </button>
                  <button
                    className="btn btn--sm btn--danger"
                    disabled={busyId === d.id}
                    onClick={() => void eliminar(d)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  Sin descuentos
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
