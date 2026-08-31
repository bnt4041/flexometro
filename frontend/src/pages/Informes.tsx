import { useCallback, useEffect, useState } from 'react'
import { BarChart3, Download, Play, Plus, Save, Table2, Trash2 } from 'lucide-react'

import { GraficoBarras } from '../components/GraficoBarras'
import { EmptyState, ErrorNotice, Field, Modal } from '../components/ui'
import { api, descargar } from '../lib/api'
import type { FilaInforme, FuenteInforme, Informe } from '../lib/api'
import { useToast } from '../toast'

/** Informes agregados: agrupar por algo y contar o sumar.
 *
 *  Lo que hay que tener presente al leerlos: cada informe se ejecuta con el
 *  alcance de permisos de QUIEN LO ABRE. Dos personas pueden abrir el mismo
 *  informe guardado y ver cifras distintas, y eso es lo correcto — la
 *  alternativa sería que un listado agregado contara lo que la pantalla
 *  niega. */
export function Informes() {
  const { notificar } = useToast()
  const [fuentes, setFuentes] = useState<FuenteInforme[]>([])
  const [guardados, setGuardados] = useState<Informe[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const [fuente, setFuente] = useState<FuenteInforme | null>(null)
  const [dimensiones, setDimensiones] = useState<string[]>([])
  const [metricas, setMetricas] = useState<string[]>([])
  const [filas, setFilas] = useState<FilaInforme[] | null>(null)
  const [grafico, setGrafico] = useState<'tabla' | 'barras'>('tabla')
  const [guardando, setGuardando] = useState(false)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const [f, g] = await Promise.all([api.informes.fuentes(), api.informes.list()])
      setFuentes(f)
      setGuardados(g)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function elegirFuente(codigo: string) {
    const nueva = fuentes.find((f) => f.codigo === codigo) ?? null
    setFuente(nueva)
    setFilas(null)
    // Se empieza con la primera dimensión y la primera métrica: un informe
    // vacío no enseña nada y obliga a adivinar por dónde se empieza.
    setDimensiones(nueva?.dimensiones[0] ? [nueva.dimensiones[0].nombre] : [])
    setMetricas(nueva?.metricas[0] ? [nueva.metricas[0].nombre] : [])
  }

  function alternar(lista: string[], valor: string, poner: (l: string[]) => void) {
    poner(lista.includes(valor) ? lista.filter((v) => v !== valor) : [...lista, valor])
    setFilas(null)
  }

  async function consultar() {
    if (!fuente || metricas.length === 0) return
    setError(null)
    try {
      const r = await api.informes.consultar({
        fuente: fuente.codigo,
        dimensiones,
        metricas,
        filtros: {},
      })
      setFilas(r.filas)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function abrir(informe: Informe) {
    setError(null)
    try {
      const r = await api.informes.ejecutar(informe.id)
      setFuente(fuentes.find((f) => f.codigo === r.informe.fuente) ?? null)
      setDimensiones(r.informe.dimensiones)
      setMetricas(r.informe.metricas)
      setGrafico(r.informe.grafico === 'barras' ? 'barras' : 'tabla')
      setFilas(r.filas)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function borrar(informe: Informe) {
    if (!window.confirm(`¿Borrar «${informe.nombre}»?`)) return
    await api.informes.remove(informe.id).catch(() => undefined)
    notificar('Informe borrado')
    await cargar()
  }

  const columnas = [...dimensiones, ...metricas]
  const campo = (nombre: string) =>
    fuente?.dimensiones.find((d) => d.nombre === nombre) ??
    fuente?.metricas.find((m) => m.nombre === nombre)

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Informes</h1>
          <p className="page-lead">
            Agrupa por lo que quieras y cuenta o suma. Cada informe se ejecuta con tus permisos:
            si solo ves lo tuyo, las cifras son solo de lo tuyo.
          </p>
        </div>
        {fuente && filas && (
          <button className="btn btn--primary" onClick={() => setGuardando(true)}>
            <Save size={16} aria-hidden="true" /> Guardar informe
          </button>
        )}
      </div>

      <ErrorNotice error={error} />

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : fuentes.length === 0 ? (
        <EmptyState title="Nada que consultar">
          No tienes permiso de ver ningún módulo con datos para informes.
        </EmptyState>
      ) : (
        <div className="card" style={{ padding: 'var(--sp-5)' }}>
          <div className="form-grid">
            <Field ancho="doble" label="Sobre qué" hint={fuente?.descripcion}>
              <select
                className="select"
                value={fuente?.codigo ?? ''}
                onChange={(e) => elegirFuente(e.target.value)}
              >
                <option value="">Elegir…</option>
                {fuentes.map((f) => (
                  <option key={f.codigo} value={f.codigo}>
                    {f.etiqueta}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {fuente && (
            <>
              <div className="form-section__title" style={{ marginTop: 'var(--sp-3)' }}>
                Agrupar por
              </div>
              <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                {fuente.dimensiones.map((d) => (
                  <button
                    key={d.nombre}
                    className={`btn btn--sm${dimensiones.includes(d.nombre) ? ' btn--primary' : ''}`}
                    onClick={() => alternar(dimensiones, d.nombre, setDimensiones)}
                  >
                    {d.etiqueta}
                  </button>
                ))}
              </div>

              <div className="form-section__title" style={{ marginTop: 'var(--sp-3)' }}>
                Y calcular
              </div>
              <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                {fuente.metricas.map((m) => (
                  <button
                    key={m.nombre}
                    className={`btn btn--sm${metricas.includes(m.nombre) ? ' btn--primary' : ''}`}
                    onClick={() => alternar(metricas, m.nombre, setMetricas)}
                  >
                    {m.etiqueta}
                  </button>
                ))}
              </div>

              <div className="form-actions">
                <button
                  className="btn btn--primary"
                  onClick={() => void consultar()}
                  disabled={metricas.length === 0}
                >
                  <Play size={16} aria-hidden="true" /> Ver resultado
                </button>
              </div>

              {metricas.length === 0 && (
                <p className="muted" style={{ fontSize: '0.85em' }}>
                  Elige al menos algo que calcular.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {filas && fuente && (
        <div className="card" style={{ padding: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
            <strong>
              {filas.length} fila{filas.length === 1 ? '' : 's'}
            </strong>
            <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
              <button
                className={`btn btn--sm${grafico === 'tabla' ? ' btn--primary' : ''}`}
                onClick={() => setGrafico('tabla')}
              >
                <Table2 size={14} aria-hidden="true" /> Tabla
              </button>
              <button
                className={`btn btn--sm${grafico === 'barras' ? ' btn--primary' : ''}`}
                onClick={() => setGrafico('barras')}
                disabled={dimensiones.length === 0}
              >
                <BarChart3 size={14} aria-hidden="true" /> Barras
              </button>
            </div>
          </div>

          {filas.length === 0 ? (
            <p className="muted" style={{ marginTop: 'var(--sp-3)' }}>
              No hay datos que cumplan esto.
            </p>
          ) : grafico === 'barras' && dimensiones[0] && metricas[0] ? (
            <div style={{ marginTop: 'var(--sp-3)' }}>
              <GraficoBarras
                filas={filas}
                dimension={campo(dimensiones[0])!}
                metrica={campo(metricas[0])!}
              />
            </div>
          ) : (
            <div className="table-wrap" style={{ marginTop: 'var(--sp-3)' }}>
              <table className="table">
                <thead>
                  <tr>
                    {columnas.map((c) => (
                      <th key={c}>{campo(c)?.etiqueta ?? c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filas.map((fila, i) => (
                    <tr key={i}>
                      {columnas.map((c) => {
                        const valor = fila[c]
                        const formato = campo(c)?.formato
                        return (
                          <td key={c} style={{ textAlign: formato === 'dinero' ? 'right' : undefined }}>
                            {valor === null || valor === undefined
                              ? '—'
                              : formato === 'dinero'
                                ? Number(valor).toLocaleString('es-ES', {
                                    minimumFractionDigits: 2,
                                  })
                                : typeof valor === 'string' && valor.includes('T')
                                  ? valor.slice(0, 7)
                                  : String(valor)}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {guardados.length > 0 && (
        <>
          <div className="form-section__title" style={{ marginTop: 'var(--sp-5)' }}>
            Informes guardados
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Informe</th>
                  <th>Sobre</th>
                  <th>De</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {guardados.map((informe) => (
                  <tr key={informe.id}>
                    <td>
                      <button className="btn-enlace" onClick={() => void abrir(informe)}>
                        {informe.nombre}
                      </button>
                      {!informe.compartido && (
                        <span className="badge" style={{ marginLeft: 6 }}>
                          solo mío
                        </span>
                      )}
                    </td>
                    <td className="muted">{informe.fuente}</td>
                    <td className="muted" style={{ fontSize: '0.85em' }}>
                      {informe.creado_por_nombre ?? '—'}
                    </td>
                    <td style={{ textAlign: 'right', display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
                      <button
                        className="btn btn--sm"
                        onClick={() =>
                          void descargar(api.informes.csvUrl(informe.id), `${informe.nombre}.csv`)
                        }
                      >
                        <Download size={13} aria-hidden="true" /> CSV
                      </button>
                      <button
                        className="btn btn--sm btn--danger"
                        onClick={() => void borrar(informe)}
                        aria-label={`Borrar ${informe.nombre}`}
                      >
                        <Trash2 size={13} aria-hidden="true" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {guardando && fuente && (
        <GuardarInforme
          fuente={fuente.codigo}
          dimensiones={dimensiones}
          metricas={metricas}
          grafico={grafico}
          onCerrar={() => setGuardando(false)}
          onGuardado={async () => {
            setGuardando(false)
            await cargar()
          }}
        />
      )}
    </div>
  )
}

function GuardarInforme({
  fuente,
  dimensiones,
  metricas,
  grafico,
  onCerrar,
  onGuardado,
}: {
  fuente: string
  dimensiones: string[]
  metricas: string[]
  grafico: string
  onCerrar: () => void
  onGuardado: () => void | Promise<void>
}) {
  const { notificar } = useToast()
  const [nombre, setNombre] = useState('')
  const [compartido, setCompartido] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    if (!nombre.trim()) {
      setError('Ponle un nombre.')
      return
    }
    try {
      await api.informes.create({
        nombre: nombre.trim(),
        fuente,
        dimensiones,
        metricas,
        filtros: {},
        grafico,
        compartido,
      })
      notificar('Informe guardado')
      await onGuardado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Guardar informe" onClose={onCerrar}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Nombre">
          <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} autoFocus />
        </Field>
        <label className="checkbox" style={{ display: 'block', marginTop: 'var(--sp-3)' }}>
          <input
            type="checkbox"
            checked={compartido}
            onChange={(e) => setCompartido(e.target.checked)}
          />
          <span>
            Visible para toda la organización{' '}
            <span className="muted" style={{ fontSize: '0.85em' }}>
              — cada uno lo verá con sus propios permisos
            </span>
          </span>
        </label>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button className="btn btn--primary" onClick={() => void guardar()}>
          <Plus size={16} aria-hidden="true" /> Guardar
        </button>
      </div>
    </Modal>
  )
}
