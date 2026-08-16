import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Field, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type { CapituloSugerido, SugerenciaDetalle } from '../lib/api'

export function IaPatrones() {
  const navegar = useNavigate()
  const [tipoObra, setTipoObra] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [sugerencia, setSugerencia] = useState<SugerenciaDetalle | null>(null)
  const [capitulos, setCapitulos] = useState<CapituloSugerido[]>([])
  const [nombrePlantilla, setNombrePlantilla] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [solicitando, setSolicitando] = useState(false)
  const [creando, setCreando] = useState(false)
  const [plantillaId, setPlantillaId] = useState<string | null>(null)

  async function solicitar() {
    setSolicitando(true)
    setError(null)
    setSugerencia(null)
    setPlantillaId(null)
    try {
      const resultado = await api.ia.solicitar({
        tipo_obra: tipoObra,
        descripcion: descripcion || null,
      })
      setSugerencia(resultado)
      setCapitulos(structuredClone(resultado.capitulos))
      setNombrePlantilla(`Plantilla — ${tipoObra}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setSolicitando(false)
    }
  }

  function quitarCapitulo(indice: number) {
    setCapitulos((actual) => actual.filter((_, i) => i !== indice))
  }

  function quitarPartida(indiceCapitulo: number, indicePartida: number) {
    setCapitulos((actual) =>
      actual.map((cap, i) =>
        i !== indiceCapitulo
          ? cap
          : { ...cap, partidas: cap.partidas.filter((_, j) => j !== indicePartida) },
      ),
    )
  }

  function editarCapitulo(indice: number, resumen: string) {
    setCapitulos((actual) =>
      actual.map((cap, i) => (i !== indice ? cap : { ...cap, resumen })),
    )
  }

  function editarPartida(
    indiceCapitulo: number,
    indicePartida: number,
    cambios: Partial<{ resumen: string; unidad: string }>,
  ) {
    setCapitulos((actual) =>
      actual.map((cap, i) =>
        i !== indiceCapitulo
          ? cap
          : {
              ...cap,
              partidas: cap.partidas.map((p, j) =>
                j !== indicePartida ? p : { ...p, ...cambios },
              ),
            },
      ),
    )
  }

  async function crearPlantilla() {
    if (!sugerencia) return
    setCreando(true)
    setError(null)
    try {
      const plantilla = await api.ia.crearPlantilla(sugerencia.id, {
        nombre: nombrePlantilla,
        capitulos: capitulos.map((cap) => ({
          resumen: cap.resumen,
          partidas: cap.partidas.map((p) => ({
            concepto_id: p.concepto_id,
            resumen: p.resumen,
            unidad: p.unidad,
          })),
        })),
      })
      setPlantillaId(plantilla.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCreando(false)
    }
  }

  const totalPartidas = capitulos.reduce((n, c) => n + c.partidas.length, 0)
  const nuevas = capitulos.reduce(
    (n, c) => n + c.partidas.filter((p) => p.es_nueva).length,
    0,
  )

  return (
    <>
      <h1 className="page-title">Sugerir patrón de presupuesto</h1>
      <p className="page-lead">
        A partir de tu histórico propio, DeepSeek propone qué capítulos y partidas suelen ir
        juntos en un tipo de obra. Solo viaja hacia la IA vocabulario estructural —tipo de obra,
        resúmenes, unidades, códigos internos—; nunca precios, importes ni datos de cliente. La
        propuesta es solo eso, una propuesta: se revisa aquí antes de convertirla en plantilla.
      </p>

      {error && <div className="notice notice--error">{error}</div>}

      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <div className="form-grid">
          <Field label="Tipo de obra" hint="Ej.: rehabilitación de fachada, reforma de baño…">
            <input
              className="input"
              value={tipoObra}
              onChange={(e) => setTipoObra(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Descripción" hint="Opcional: detalles que ayuden a afinar la propuesta">
            <input
              className="input"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
            />
          </Field>
        </div>
        <div className="form-actions">
          <button
            className="btn btn--primary"
            disabled={solicitando || tipoObra.trim() === ''}
            onClick={() => void solicitar()}
          >
            {solicitando ? 'Consultando a DeepSeek…' : 'Sugerir patrón'}
          </button>
        </div>
      </div>

      {sugerencia && (
        <>
          <div
            className="page-head"
            style={{ marginTop: 'var(--sp-6)', marginBottom: 'var(--sp-3)' }}
          >
            <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>
              Propuesta — revisa antes de crear la plantilla
            </h2>
            <span className="badge">
              {totalPartidas} partidas{nuevas > 0 && `, ${nuevas} nuevas sin tarifar`}
            </span>
          </div>

          {capitulos.length === 0 ? (
            <div className="notice notice--aviso">
              Has quitado todos los capítulos. No hay nada que crear.
            </div>
          ) : (
            capitulos.map((capitulo, i) => (
              <div key={i} className="card" style={{ marginBottom: 'var(--sp-3)' }}>
                <div className="form-actions" style={{ justifyContent: 'space-between' }}>
                  <input
                    className="input"
                    style={{ fontWeight: 650, maxWidth: '400px' }}
                    value={capitulo.resumen}
                    onChange={(e) => editarCapitulo(i, e.target.value)}
                  />
                  <button className="btn btn--sm btn--danger" onClick={() => quitarCapitulo(i)}>
                    Quitar capítulo
                  </button>
                </div>
                <div className="table-wrap">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Resumen</th>
                        <th>Unidad</th>
                        <th className="table__num">Precio ref.</th>
                        <th />
                        <th className="table__actions" />
                      </tr>
                    </thead>
                    <tbody>
                      {capitulo.partidas.map((partida, j) => (
                        <tr key={j}>
                          <td>
                            <input
                              className="input"
                              value={partida.resumen}
                              onChange={(e) =>
                                editarPartida(i, j, { resumen: e.target.value })
                              }
                            />
                          </td>
                          <td>
                            <input
                              className="input"
                              style={{ width: '80px' }}
                              value={partida.unidad}
                              onChange={(e) =>
                                editarPartida(i, j, { unidad: e.target.value })
                              }
                            />
                          </td>
                          <td className="table__num muted">
                            {partida.precio ? `${formatoImporte(partida.precio)} €` : '—'}
                          </td>
                          <td>
                            {partida.es_nueva ? (
                              <span className="badge">nueva, sin tarifar</span>
                            ) : (
                              <span className="muted table__code">{partida.codigo}</span>
                            )}
                          </td>
                          <td className="table__actions">
                            <button
                              className="btn btn--sm btn--danger"
                              onClick={() => quitarPartida(i, j)}
                            >
                              ×
                            </button>
                          </td>
                        </tr>
                      ))}
                      {capitulo.partidas.length === 0 && (
                        <tr>
                          <td colSpan={5} className="muted">
                            Sin partidas
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            ))
          )}

          <div className="card" style={{ padding: 'var(--sp-5)' }}>
            <div className="form-section__note">
              Las partidas marcadas "nueva, sin tarifar" se crearán como conceptos reales del
              cuadro de precios (origen IA, precio 0,00 €): revísalas y ponles precio antes de
              usarlas en una obra real.
            </div>
            <div className="form-grid" style={{ marginTop: 'var(--sp-3)' }}>
              <Field label="Nombre de la plantilla">
                <input
                  className="input"
                  value={nombrePlantilla}
                  onChange={(e) => setNombrePlantilla(e.target.value)}
                />
              </Field>
            </div>
            <div className="form-actions">
              {plantillaId ? (
                <button
                  className="btn btn--primary"
                  onClick={() => navegar(`/presupuestos/${plantillaId}`)}
                >
                  Ver la plantilla creada
                </button>
              ) : (
                <button
                  className="btn btn--primary"
                  disabled={creando || capitulos.length === 0 || nombrePlantilla.trim() === ''}
                  onClick={() => void crearPlantilla()}
                >
                  {creando ? 'Creando…' : 'Crear plantilla'}
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}
