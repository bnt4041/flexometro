import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { Checkbox, EmptyState, ErrorNotice, Field } from '../components/ui'
import { api } from '../lib/api'
import type { AnalisisBC3, ImportacionBC3 } from '../lib/api'

const ETIQUETA_TIPO: Record<string, string> = {
  raiz: 'Raíz de obra',
  capitulo: 'Capítulos',
  unitario: 'Unitarios',
  auxiliar: 'Auxiliares',
  basico: 'Básicos',
}

export function ImportarBC3() {
  const navegar = useNavigate()
  const [fichero, setFichero] = useState<File | null>(null)
  const [analisis, setAnalisis] = useState<AnalisisBC3 | null>(null)
  const [resultado, setResultado] = useState<ImportacionBC3 | null>(null)
  const [estrategia, setEstrategia] = useState('omitir')
  const [crearPresupuesto, setCrearPresupuesto] = useState(true)
  const [nombre, setNombre] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [trabajando, setTrabajando] = useState(false)

  async function elegir(elegido: File | null) {
    setFichero(elegido)
    setAnalisis(null)
    setResultado(null)
    setError(null)
    if (!elegido) return

    setTrabajando(true)
    try {
      setAnalisis(await api.fiebdc.analizar(elegido))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setTrabajando(false)
    }
  }

  async function importar() {
    if (!fichero) return
    setTrabajando(true)
    setError(null)
    try {
      setResultado(
        await api.fiebdc.importar(fichero, {
          estrategia,
          crear_presupuesto: crearPresupuesto,
          nombre_presupuesto: nombre || undefined,
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setTrabajando(false)
    }
  }

  return (
    <>
      <h1 className="page-title">Importar BC3</h1>
      <p className="page-lead">
        Formato FIEBDC-3, el que usan Presto, Arquímedes y los bancos de precios oficiales.
        Primero se analiza el fichero sin escribir nada; la importación es un segundo paso.
      </p>

      <ErrorNotice error={error} />

      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <Field label="Fichero BC3">
          <input
            className="input"
            type="file"
            accept=".bc3,.BC3"
            onChange={(e) => void elegir(e.target.files?.[0] ?? null)}
          />
        </Field>
        {trabajando && !analisis && (
          <p className="muted" style={{ marginTop: 'var(--sp-3)' }}>
            Leyendo el fichero…
          </p>
        )}
      </div>

      {analisis && (
        <>
          <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, margin: 'var(--sp-6) 0 var(--sp-3)' }}>
            Qué trae el fichero
          </h2>

          <div className="card" style={{ padding: 'var(--sp-5)' }}>
            <div className="ficha-datos">
              <Dato etiqueta="Versión" valor={analisis.version || '—'} />
              <Dato etiqueta="Emitido por" valor={analisis.programa || '—'} />
              <Dato etiqueta="Codificación" valor={analisis.codificacion} />
              <Dato
                etiqueta="Contenido"
                valor={analisis.es_presupuesto ? 'Obra con capítulos' : 'Banco de precios'}
              />
              <Dato etiqueta="Conceptos" valor={String(analisis.total_conceptos)} />
              <Dato
                etiqueta="Descomposición"
                valor={`${analisis.lineas_descomposicion} líneas`}
              />
              <Dato etiqueta="Mediciones" valor={String(analisis.mediciones)} />
            </div>

            {analisis.cabecera && (
              <p className="muted" style={{ marginTop: 'var(--sp-4)' }}>
                {analisis.cabecera}
              </p>
            )}

            <div style={{ marginTop: 'var(--sp-5)' }}>
              <div className="barra-acciones__etiqueta">Clasificación por estructura</div>
              <div className="chips" style={{ marginTop: 'var(--sp-2)' }}>
                {Object.entries(analisis.por_tipo).map(([tipo, cuantos]) => (
                  <span key={tipo} className="badge">
                    {ETIQUETA_TIPO[tipo] ?? tipo}: {cuantos}
                  </span>
                ))}
              </div>
              <p className="field__hint" style={{ marginTop: 'var(--sp-2)' }}>
                El nivel de cada precio se deduce de quién descompone a quién, no del sufijo del
                código: es más fiable que confiar en que el banco respete las convenciones.
              </p>
            </div>

            {analisis.incidencias.length > 0 && (
              <div style={{ marginTop: 'var(--sp-5)' }}>
                <div className="barra-acciones__etiqueta">
                  No interpretado ({analisis.incidencias.length})
                </div>
                <ul className="lista-incidencias">
                  {analisis.incidencias.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="card" style={{ marginTop: 'var(--sp-5)' }}>
            <div className="form-section">
              <div className="form-section__title">Importar</div>
              <div className="form-grid">
                <Field
                  label="Códigos que ya existan"
                  hint="Se comparan por código dentro de tu organización"
                >
                  <select
                    className="select"
                    value={estrategia}
                    onChange={(e) => setEstrategia(e.target.value)}
                  >
                    <option value="omitir">Respetar lo que ya tengo</option>
                    <option value="actualizar">Pisar con los datos del fichero</option>
                  </select>
                </Field>
                {analisis.es_presupuesto && crearPresupuesto && (
                  <Field label="Nombre del presupuesto" hint="Vacío: el del propio fichero">
                    <input
                      className="input"
                      value={nombre}
                      onChange={(e) => setNombre(e.target.value)}
                    />
                  </Field>
                )}
              </div>
              {analisis.es_presupuesto && (
                <div style={{ marginTop: 'var(--sp-4)' }}>
                  <Checkbox
                    label="Crear también el presupuesto con sus capítulos y mediciones"
                    checked={crearPresupuesto}
                    onChange={setCrearPresupuesto}
                  />
                </div>
              )}
            </div>
            <div className="form-actions">
              <button
                className="btn btn--primary"
                disabled={trabajando}
                onClick={() => void importar()}
              >
                {trabajando ? 'Importando…' : 'Importar'}
              </button>
            </div>
          </div>
        </>
      )}

      {resultado && (
        <>
          <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650, margin: 'var(--sp-6) 0 var(--sp-3)' }}>
            Resultado
          </h2>

          <div className="card" style={{ padding: 'var(--sp-5)' }}>
            <div className="ficha-datos">
              <Dato etiqueta="Conceptos creados" valor={String(resultado.conceptos_creados)} />
              <Dato etiqueta="Omitidos" valor={String(resultado.conceptos_omitidos)} />
              <Dato etiqueta="Actualizados" valor={String(resultado.conceptos_actualizados)} />
              <Dato
                etiqueta="Descomposición"
                valor={`${resultado.lineas_descomposicion} líneas`}
              />
              {resultado.presupuesto_id && (
                <>
                  <Dato etiqueta="Capítulos" valor={String(resultado.capitulos)} />
                  <Dato etiqueta="Partidas" valor={String(resultado.partidas)} />
                  <Dato
                    etiqueta="Líneas de medición"
                    valor={String(resultado.lineas_medicion)}
                  />
                </>
              )}
            </div>

            {resultado.presupuesto_id && (
              <button
                className="btn btn--primary"
                style={{ marginTop: 'var(--sp-4)' }}
                onClick={() => navegar(`/presupuestos/${resultado.presupuesto_id}`)}
              >
                Ver el presupuesto importado
              </button>
            )}
          </div>

          {resultado.discrepancias > 0 && (
            <div className="card" style={{ marginTop: 'var(--sp-4)', padding: 'var(--sp-5)' }}>
              <div className="form-section__title">
                {resultado.discrepancias} precios no cuadran con su descomposición
              </div>
              <p className="form-section__note">
                El fichero declara un precio distinto del que sale al sumar sus componentes con
                nuestro redondeo. Diferencia mayor: {resultado.discrepancia_maxima} €. Se ha
                guardado el calculado, que es el que cuadra con el descompuesto impreso.
              </p>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Código</th>
                      <th className="table__num">Calculado</th>
                      <th className="table__num">En el fichero</th>
                    </tr>
                  </thead>
                  <tbody>
                    {resultado.ejemplos_discrepancia.map((d) => (
                      <tr key={d.codigo}>
                        <td className="table__code">{d.codigo}</td>
                        <td className="table__num">{d.calculado}</td>
                        <td className="table__num muted">{d.en_fichero}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {resultado.incidencias.length > 0 && (
            <div className="card" style={{ marginTop: 'var(--sp-4)', padding: 'var(--sp-5)' }}>
              <div className="barra-acciones__etiqueta">
                Incidencias ({resultado.incidencias.length})
              </div>
              <ul className="lista-incidencias">
                {resultado.incidencias.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {!analisis && !fichero && (
        <div style={{ marginTop: 'var(--sp-5)' }}>
          <EmptyState title="Elige un fichero para empezar">
            Se admiten bancos de precios y obras completas. Nada se escribe hasta que lo
            confirmes.
          </EmptyState>
        </div>
      )}
    </>
  )
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div>
      <div className="barra-acciones__etiqueta">{etiqueta}</div>
      <div className="ficha-datos__valor">{valor}</div>
    </div>
  )
}
