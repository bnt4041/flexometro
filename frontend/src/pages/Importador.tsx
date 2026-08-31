import { useCallback, useEffect, useState } from 'react'
import { Play } from 'lucide-react'

import { EmptyState, ErrorNotice, Field } from '../components/ui'
import { api } from '../lib/api'
import type { DestinoImportacion, Importacion } from '../lib/api'
import { useToast } from '../toast'

/** Traer datos de otro sistema desde una hoja.
 *
 *  Tres pasos y en este orden: subir, cuadrar columnas, importar. El paso de
 *  en medio existe porque nadie tiene la hoja con los nombres que espera
 *  Flexómetro, y porque ver los problemas ANTES de escribir es la diferencia
 *  entre corregir la hoja y tener que limpiar la base después. */
export function Importador() {
  const { notificar } = useToast()
  const [destinos, setDestinos] = useState<DestinoImportacion[]>([])
  const [destino, setDestino] = useState('')
  const [actual, setActual] = useState<Importacion | null>(null)
  const [historico, setHistorico] = useState<Importacion[]>([])
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const [d, h] = await Promise.all([api.importador.destinos(), api.importador.list()])
      setDestinos(d)
      setHistorico(h.filter((i) => i.estado !== 'preparada'))
      if (!destino && d[0]) setDestino(d[0].codigo)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
    // `destino` fuera de las dependencias: solo se usa para elegir el primero
    // la primera vez, y meterlo aquí recargaría todo a cada cambio.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const destinoActual = destinos.find((d) => d.codigo === (actual?.destino ?? destino))

  async function subir(archivo: File) {
    setOcupado(true)
    setError(null)
    try {
      setActual(await api.importador.subir(destino, archivo))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  async function cambiarMapeo(campo: string, columna: string) {
    if (!actual) return
    const mapeo = { ...actual.mapeo, [campo]: columna }
    if (!columna) delete mapeo[campo]
    try {
      setActual(await api.importador.mapeo(actual.id, mapeo))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function ejecutar() {
    if (!actual) return
    setOcupado(true)
    setError(null)
    try {
      const hecha = await api.importador.ejecutar(actual.id)
      setActual(hecha)
      notificar(`${hecha.creadas} creadas, ${hecha.con_error} con error`)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  const yaEjecutada = actual !== null && actual.estado !== 'preparada'

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Importador</h1>
          <p className="page-lead">
            Trae datos desde una hoja de CSV o Excel. Se comprueba todo antes de escribir nada, y
            se importa fila a fila: si una falla, las demás entran igual.
          </p>
        </div>
      </div>

      <ErrorNotice error={error} />

      {!actual && (
        <div className="card" style={{ padding: 'var(--sp-5)' }}>
          <div className="form-grid">
            <Field ancho="doble" label="¿Qué vas a importar?" hint={destinoActual?.descripcion}>
              <select
                className="select"
                value={destino}
                onChange={(e) => setDestino(e.target.value)}
              >
                {destinos.map((d) => (
                  <option key={d.codigo} value={d.codigo}>
                    {d.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="La hoja" hint=".csv, .xlsx — hasta 5.000 filas">
              <input
                className="input"
                type="file"
                accept=".csv,.xlsx,.xlsm,.txt"
                disabled={ocupado || !destino}
                onChange={(e) => {
                  const archivo = e.target.files?.[0]
                  if (archivo) void subir(archivo)
                }}
              />
            </Field>
          </div>
          {destinoActual && (
            <p className="muted" style={{ fontSize: '0.85em' }}>
              Campos que se pueden rellenar:{' '}
              {destinoActual.campos
                .map((c) => c.etiqueta + (c.obligatorio ? ' (obligatorio)' : ''))
                .join(', ')}
              .
            </p>
          )}
        </div>
      )}

      {actual && destinoActual && (
        <div className="card" style={{ padding: 'var(--sp-5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
            <div>
              <strong>{actual.nombre_archivo}</strong>
              <div className="muted" style={{ fontSize: '0.9em' }}>
                {actual.total_filas} fila{actual.total_filas === 1 ? '' : 's'} ·{' '}
                {destinoActual.etiqueta}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <button className="btn" onClick={() => setActual(null)}>
                Empezar otra
              </button>
              {!yaEjecutada && (
                <button
                  className="btn btn--primary"
                  onClick={() => void ejecutar()}
                  disabled={ocupado}
                >
                  <Play size={16} aria-hidden="true" />
                  {ocupado ? 'Importando…' : `Importar ${actual.total_filas}`}
                </button>
              )}
            </div>
          </div>

          {!yaEjecutada ? (
            <>
              <div className="form-section__title" style={{ marginTop: 'var(--sp-4)' }}>
                Cuadrar columnas
              </div>
              <p className="form-section__note">
                Se han emparejado solas las que coincidían. Revisa el resto.
              </p>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Campo de Flexómetro</th>
                      <th>Columna de tu hoja</th>
                      <th>Ejemplo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {destinoActual.campos.map((campo) => {
                      const columna = actual.mapeo[campo.nombre] ?? ''
                      const ejemplo = columna ? actual.vista_previa[0]?.[columna] : ''
                      return (
                        <tr key={campo.nombre}>
                          <td>
                            {campo.etiqueta}
                            {campo.obligatorio && (
                              <span className="badge badge--danger" style={{ marginLeft: 6 }}>
                                obligatorio
                              </span>
                            )}
                            {campo.ayuda && (
                              <div className="muted" style={{ fontSize: '0.8em' }}>
                                {campo.ayuda}
                              </div>
                            )}
                          </td>
                          <td>
                            <select
                              className="select"
                              value={columna}
                              onChange={(e) => void cambiarMapeo(campo.nombre, e.target.value)}
                            >
                              <option value="">— no importar —</option>
                              {actual.columnas.map((c) => (
                                <option key={c} value={c}>
                                  {c}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td className="muted" style={{ fontSize: '0.85em' }}>
                            {ejemplo || '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {actual.problemas.length > 0 && (
                <div className="notice notice--error" style={{ marginTop: 'var(--sp-3)' }}>
                  <strong>
                    {actual.problemas.length} fila{actual.problemas.length === 1 ? '' : 's'} con
                    problemas.
                  </strong>{' '}
                  Se saltarán; las demás entrarán igual.
                  <ul style={{ margin: '6px 0 0 18px' }}>
                    {actual.problemas.slice(0, 8).map((p) => (
                      <li key={p.fila}>
                        Fila {p.fila}: {p.detalle}
                      </li>
                    ))}
                  </ul>
                  {actual.problemas.length > 8 && (
                    <div className="muted" style={{ fontSize: '0.85em' }}>
                      … y {actual.problemas.length - 8} más.
                    </div>
                  )}
                </div>
              )}

              <p className="muted" style={{ fontSize: '0.85em', marginTop: 'var(--sp-2)' }}>
                Esto comprueba lo que se puede saber sin tocar la base. Un código repetido o una
                empresa que no existe solo aparecen al importar.
              </p>
            </>
          ) : (
            <>
              <div className="form-section__title" style={{ marginTop: 'var(--sp-4)' }}>
                Resultado
              </div>
              <p>
                <strong>{actual.creadas}</strong> creadas ·{' '}
                <strong>{actual.con_error}</strong> con error
              </p>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Fila</th>
                      <th>Resultado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {actual.resultado.map((r) => (
                      <tr key={r.fila}>
                        <td>{r.fila}</td>
                        <td>
                          <span
                            className={`notice ${r.estado === 'ok' ? 'notice--ok' : 'notice--error'}`}
                            style={{ margin: 0, padding: '1px 7px', fontSize: '0.8em' }}
                          >
                            {r.estado}
                          </span>{' '}
                          {r.detalle}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {!actual && historico.length > 0 && (
        <>
          <div className="form-section__title" style={{ marginTop: 'var(--sp-5)' }}>
            Importaciones anteriores
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Fichero</th>
                  <th>Destino</th>
                  <th>Resultado</th>
                  <th>Cuándo</th>
                </tr>
              </thead>
              <tbody>
                {historico.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <button className="btn-enlace" onClick={() => setActual(i)}>
                        {i.nombre_archivo}
                      </button>
                    </td>
                    <td className="muted">{i.destino}</td>
                    <td>
                      {i.creadas} creadas
                      {i.con_error > 0 && `, ${i.con_error} con error`}
                    </td>
                    <td className="muted" style={{ fontSize: '0.85em' }}>
                      {new Date(i.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!actual && historico.length === 0 && destinos.length === 0 && (
        <EmptyState title="Sin destinos">No hay nada que se pueda importar todavía.</EmptyState>
      )}
    </div>
  )
}
