import { useCallback, useEffect, useMemo, useState } from 'react'
import { Ban, Check } from 'lucide-react'

import { ErrorNotice, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { AplicacionDescuento, Descuento } from '../lib/api'
import { ETIQUETA_MOTIVO, ETIQUETA_TIPO } from './DescuentosCard'

/** Descuentos aplicados a una cuenta: histórico completo (aplicado,
 *  anulado, vigente), anular el que esté en vigor, y aplicar uno nuevo
 *  seleccionándolo del catálogo (creado en Tarifas) — aquí no se crean
 *  descuentos nuevos, solo se buscan y se aplican.
 *
 *  Desde la Fase 14 la facturación SaaS es por cuenta, no por organización
 *  (varias organizaciones de la misma cuenta comparten un único contrato). */
export function AplicacionesDescuentoCard({ cuentaId }: { cuentaId: string }) {
  const [aplicaciones, setAplicaciones] = useState<AplicacionDescuento[]>([])
  const [catalogo, setCatalogo] = useState<Descuento[]>([])
  const [busqueda, setBusqueda] = useState('')
  const [seleccionados, setSeleccionados] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [aplicando, setAplicando] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    try {
      const [aplicacionesRes, catalogoRes] = await Promise.all([
        api.admin.cuentas.descuentos.list(cuentaId),
        api.admin.descuentos.list(),
      ])
      setAplicaciones(aplicacionesRes)
      setCatalogo(catalogoRes)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [cuentaId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const idsVigentes = useMemo(
    () => new Set(aplicaciones.filter((a) => a.vigente).map((a) => a.descuento.id)),
    [aplicaciones],
  )

  const disponibles = useMemo(() => {
    const texto = busqueda.trim().toLowerCase()
    return catalogo
      .filter((d) => d.activo && !idsVigentes.has(d.id))
      .filter((d) => !texto || d.nombre.toLowerCase().includes(texto))
  }, [catalogo, idsVigentes, busqueda])

  function toggleSeleccion(id: string) {
    setSeleccionados((actual) =>
      actual.includes(id) ? actual.filter((s) => s !== id) : [...actual, id],
    )
  }

  async function aplicar() {
    if (seleccionados.length === 0) return
    setAplicando(true)
    setError(null)
    try {
      await api.admin.cuentas.descuentos.aplicar(cuentaId, seleccionados)
      setSeleccionados([])
      setBusqueda('')
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setAplicando(false)
    }
  }

  async function anular(aplicacion: AplicacionDescuento) {
    setBusyId(aplicacion.id)
    setError(null)
    try {
      await api.admin.cuentas.descuentos.anular(cuentaId, aplicacion.id)
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

      <div className="form-section__title">Aplicar un descuento del catálogo</div>
      <input
        className="input"
        style={{ marginTop: 'var(--sp-2)' }}
        placeholder="Buscar por nombre…"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
      />
      <div
        className="table-wrap"
        style={{ marginTop: 'var(--sp-2)', maxHeight: '220px', overflowY: 'auto' }}
      >
        <table className="table">
          <tbody>
            {disponibles.map((d) => (
              <tr key={d.id}>
                <td style={{ width: '32px' }}>
                  <input
                    type="checkbox"
                    checked={seleccionados.includes(d.id)}
                    onChange={() => toggleSeleccion(d.id)}
                  />
                </td>
                <td>{d.nombre}</td>
                <td className="muted">{ETIQUETA_MOTIVO[d.motivo]}</td>
                <td className="muted">{ETIQUETA_TIPO[d.tipo]}</td>
                <td className="table__num">
                  {formatoImporte(d.valor)} {d.tipo === 'porcentaje' ? '%' : '€'}
                </td>
              </tr>
            ))}
            {disponibles.length === 0 && (
              <tr>
                <td className="muted">
                  {catalogo.length === 0
                    ? 'No hay descuentos en el catálogo todavía (se crean desde Tarifas).'
                    : 'Ningún descuento disponible con ese criterio.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="form-actions">
        <button
          className="btn btn--primary"
          disabled={aplicando || seleccionados.length === 0}
          onClick={() => void aplicar()}
        >
          {!aplicando && <Check size={16} aria-hidden="true" />}
          {aplicando
            ? 'Aplicando…'
            : `Aplicar${seleccionados.length > 0 ? ` (${seleccionados.length})` : ''}`}
        </button>
      </div>

      <div className="form-section__title" style={{ marginTop: 'var(--sp-5)' }}>
        Histórico
      </div>
      <div className="table-wrap" style={{ marginTop: 'var(--sp-2)' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Motivo</th>
              <th>Tipo</th>
              <th className="table__num">Valor</th>
              <th>Aplicado</th>
              <th>Anulado</th>
              <th>Estado</th>
              <th className="table__actions" />
            </tr>
          </thead>
          <tbody>
            {aplicaciones.map((a) => (
              <tr key={a.id}>
                <td>{a.descuento.nombre}</td>
                <td className="muted">{ETIQUETA_MOTIVO[a.descuento.motivo]}</td>
                <td className="muted">{ETIQUETA_TIPO[a.descuento.tipo]}</td>
                <td className="table__num">
                  {formatoImporte(a.descuento.valor)} {a.descuento.tipo === 'porcentaje' ? '%' : '€'}
                </td>
                <td className="muted">{a.aplicado_en.slice(0, 10)}</td>
                <td className="muted">{a.anulado_en ? a.anulado_en.slice(0, 10) : '—'}</td>
                <td>
                  <span className={`chip ${a.vigente ? 'chip--proveedor' : 'chip--inactivo'}`}>
                    {a.vigente ? 'vigente' : 'anulado'}
                  </span>
                </td>
                <td className="table__actions">
                  {a.vigente && (
                    <button
                      className="btn btn--sm btn--danger"
                      disabled={busyId === a.id}
                      onClick={() => void anular(a)}
                    >
                      {busyId !== a.id && <Ban size={14} aria-hidden="true" />}
                      {busyId === a.id ? '...' : 'Anular'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {aplicaciones.length === 0 && (
              <tr>
                <td colSpan={8} className="muted">
                  Sin descuentos aplicados
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
