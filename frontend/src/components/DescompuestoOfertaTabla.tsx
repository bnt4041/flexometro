import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { apiPublico } from '../lib/api'
import type { DatosComponente, DescompuestoOferta, Separata } from '../lib/api'

/** Las mismas naturalezas que usa el banco de precios (`NaturalezaConcepto`),
 *  pero como texto libre: el proveedor no toca el banco del emisor. */
const NATURALEZAS = [
  { valor: 'mano_obra', etiqueta: 'Mano de obra' },
  { valor: 'maquinaria', etiqueta: 'Maquinaria' },
  { valor: 'material', etiqueta: 'Material' },
  { valor: 'servicio', etiqueta: 'Servicio' },
  { valor: 'otro', etiqueta: 'Otro' },
]

const NUMEROS = [
  { id: 'rendimiento', etiqueta: 'Rendim.' },
  { id: 'precio', etiqueta: 'Precio' },
] as const

function normalizar(valor: string): string | null {
  const limpio = valor.trim().replace(',', '.')
  return limpio === '' ? null : limpio
}

/** Cómo desglosa el proveedor su precio: mano de obra, materiales, medios.
 *
 *  Mismo paradigma que el descompuesto de una partida, pero sin banco de
 *  precios detrás — son conceptos suyos, texto libre. Mientras haya
 *  componentes, el precio de la línea es la suma y deja de teclearse a mano;
 *  lo calcula el servidor para que no pueda discrepar de lo guardado. */
export function DescompuestoOfertaTabla({
  token,
  linea,
  soloLectura,
  onSeparata,
}: {
  token: string
  linea: { id: string; unidad: string; descompuesto: DescompuestoOferta[]; precio_ofertado: string | null }
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

  function alSalir(c: DescompuestoOferta, campo: keyof DatosComponente, valor: string) {
    const esNumero = campo === 'rendimiento' || campo === 'precio' || campo === 'factor'
    const actual = (c[campo as keyof DescompuestoOferta] ?? null) as string | null
    const nuevo = esNumero ? normalizar(valor) : valor.trim() || null
    const igual = esNumero
      ? Number(actual ?? NaN) === Number(nuevo ?? NaN)
      : (actual ?? '') === (nuevo ?? '')
    if (igual) return
    // Solo el campo que cambia: el backend lo trata como un PATCH real.
    void ejecutar(() => apiPublico.descompuesto.update(token, c.id, { [campo]: nuevo }))
  }

  return (
    <div className="mediciones-oferta">
      {error && <div className="notice notice--error">{error}</div>}

      <table className="table">
        <thead>
          <tr>
            <th>Descripción</th>
            <th>Tipo</th>
            <th>Ud</th>
            {NUMEROS.map((n) => (
              <th key={n.id}>{n.etiqueta}</th>
            ))}
            <th>Importe</th>
            {!soloLectura && <th />}
          </tr>
        </thead>
        <tbody>
          {linea.descompuesto.map((c) => (
            <tr key={c.id}>
              <td>
                <input
                  className="input"
                  defaultValue={c.resumen}
                  placeholder="Oficial 1ª, pasta de yeso…"
                  disabled={soloLectura}
                  onBlur={(e) => alSalir(c, 'resumen', e.target.value)}
                />
              </td>
              <td>
                <select
                  className="select"
                  defaultValue={c.naturaleza ?? ''}
                  disabled={soloLectura}
                  onChange={(e) => alSalir(c, 'naturaleza', e.target.value)}
                >
                  <option value="">—</option>
                  {NATURALEZAS.map((n) => (
                    <option key={n.valor} value={n.valor}>
                      {n.etiqueta}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  className="input"
                  defaultValue={c.unidad}
                  disabled={soloLectura}
                  onBlur={(e) => alSalir(c, 'unidad', e.target.value)}
                  style={{ width: '4.5rem' }}
                />
              </td>
              {NUMEROS.map((n) => (
                <td key={n.id}>
                  <input
                    className="input"
                    inputMode="decimal"
                    defaultValue={c[n.id]}
                    disabled={soloLectura}
                    onBlur={(e) => alSalir(c, n.id, e.target.value)}
                    style={{ width: '6rem' }}
                  />
                </td>
              ))}
              <td className="table__num">{c.importe}</td>
              {!soloLectura && (
                <td className="table__actions">
                  <button
                    className="btn btn--sm"
                    disabled={ocupado}
                    aria-label="Quitar este componente"
                    onClick={() => void ejecutar(() => apiPublico.descompuesto.remove(token, c.id))}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </td>
              )}
            </tr>
          ))}
          {linea.descompuesto.length === 0 && (
            <tr>
              <td colSpan={7} className="muted">
                Sin desglosar. Si prefieres justificar de qué se compone tu precio, detállalo aquí
                y el precio unitario se calculará solo.
              </td>
            </tr>
          )}
        </tbody>
        {linea.descompuesto.length > 0 && (
          <tfoot>
            <tr>
              <td colSpan={5}>
                <strong>Precio unitario resultante</strong>
              </td>
              <td className="table__num">
                <strong>
                  {linea.precio_ofertado} €/{linea.unidad}
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
          onClick={() =>
            void ejecutar(() => apiPublico.descompuesto.add(token, linea.id, { resumen: '' }))
          }
        >
          <Plus size={14} aria-hidden="true" />
          Añadir componente
        </button>
      )}
    </div>
  )
}
