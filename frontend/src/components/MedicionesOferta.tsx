import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { apiPublico } from '../lib/api'
import type { DatosMedicion, MedicionOferta, Separata } from '../lib/api'

const CAMPOS = [
  { id: 'uds', etiqueta: 'Uds' },
  { id: 'longitud', etiqueta: 'Largo' },
  { id: 'anchura', etiqueta: 'Ancho' },
  { id: 'altura', etiqueta: 'Alto' },
] as const

function normalizar(valor: string): string | null {
  const limpio = valor.trim().replace(',', '.')
  return limpio === '' ? null : limpio
}

/** El estado de mediciones que aporta el proveedor para una línea, con el
 *  mismo paradigma que un presupuesto: comentario, uds, largo, ancho y alto,
 *  y el parcial como producto de lo que se informe (lo que se deja en blanco
 *  vale 1, no 0).
 *
 *  Cada cambio devuelve la separata entera ya recalculada en el servidor: el
 *  parcial y la suma no se calculan aquí para que no puedan discrepar de lo
 *  que se guarda. */
export function MedicionesOferta({
  token,
  linea,
  soloLectura,
  onSeparata,
}: {
  token: string
  linea: { id: string; unidad: string; mediciones: MedicionOferta[]; medicion_proveedor: string | null }
  soloLectura: boolean
  onSeparata: (s: Separata) => void
}) {
  const [ocupado, setOcupado] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function ejecutar(accion: () => Promise<Separata>) {
    setOcupado(true)
    setError(null)
    try {
      onSeparata(await accion())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  function alSalirDeCampo(medicion: MedicionOferta, campo: keyof DatosMedicion, valor: string) {
    const actual = (medicion[campo as keyof MedicionOferta] ?? null) as string | null
    const nuevo = campo === 'comentario' ? valor.trim() || null : normalizar(valor)
    // `12.50` y `12.5` son el mismo número: comparar en crudo dispararía una
    // petición cada vez que el cursor pasa por una casilla ya guardada.
    const igual =
      campo === 'comentario'
        ? (actual ?? '') === (nuevo ?? '')
        : Number(actual ?? NaN) === Number(nuevo ?? NaN) ||
          (actual === null && nuevo === null)
    if (igual) return

    // Solo el campo que ha cambiado: el backend lo trata como un PATCH real,
    // así que dos ediciones seguidas no se pisan con valores viejos.
    void ejecutar(() => apiPublico.mediciones.update(token, medicion.id, { [campo]: nuevo }))
  }

  return (
    <div className="mediciones-oferta">
      {error && <div className="notice notice--error">{error}</div>}

      <table className="table">
        <thead>
          <tr>
            <th>Descripción</th>
            {CAMPOS.map((c) => (
              <th key={c.id}>{c.etiqueta}</th>
            ))}
            <th>Parcial</th>
            {!soloLectura && <th />}
          </tr>
        </thead>
        <tbody>
          {linea.mediciones.map((m) => (
            <tr key={m.id}>
              <td>
                {/* Sin `disabled` mientras guarda: deshabilitar una casilla
                    con el cursor dentro corta el tecleo y hace que una tanda
                    de ediciones seguidas se pierda por el camino. */}
                <input
                  className="input"
                  defaultValue={m.comentario ?? ''}
                  placeholder="Planta baja, fachada norte…"
                  disabled={soloLectura}
                  onBlur={(e) => alSalirDeCampo(m, 'comentario', e.target.value)}
                />
              </td>
              {CAMPOS.map((c) => (
                <td key={c.id}>
                  <input
                    className="input"
                    inputMode="decimal"
                    defaultValue={(m[c.id] ?? '') as string}
                    disabled={soloLectura}
                    onBlur={(e) => alSalirDeCampo(m, c.id, e.target.value)}
                    style={{ width: '5.5rem' }}
                  />
                </td>
              ))}
              <td className="table__num">{m.parcial}</td>
              {!soloLectura && (
                <td className="table__actions">
                  <button
                    className="btn btn--sm"
                    disabled={ocupado}
                    aria-label="Quitar este parcial"
                    onClick={() => void ejecutar(() => apiPublico.mediciones.remove(token, m.id))}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </td>
              )}
            </tr>
          ))}
          {linea.mediciones.length === 0 && (
            <tr>
              <td colSpan={7} className="muted">
                Sin medir. Si tu medición no coincide con la pedida, detállala aquí.
              </td>
            </tr>
          )}
        </tbody>
        {linea.medicion_proveedor !== null && (
          <tfoot>
            <tr>
              <td colSpan={5}>
                <strong>Total medido</strong>
              </td>
              <td className="table__num">
                <strong>
                  {linea.medicion_proveedor} {linea.unidad}
                </strong>
              </td>
              {!soloLectura && <td />}
            </tr>
          </tfoot>
        )}
      </table>

      {!soloLectura && (
        <button
          className="btn btn--sm"
          disabled={ocupado}
          onClick={() => void ejecutar(() => apiPublico.mediciones.add(token, linea.id, {}))}
        >
          <Plus size={14} aria-hidden="true" />
          Añadir parcial
        </button>
      )}
    </div>
  )
}
