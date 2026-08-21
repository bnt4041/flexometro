import { useEffect, useState } from 'react'
import { Check, ChevronRight, FileUp, X } from 'lucide-react'

import { ErrorNotice, Modal } from './ui'
import { api } from '../lib/api'
import type { AnalisisBC3, ImportacionBC3 } from '../lib/api'

/** Arrastrar uno o varios BC3 sobre un capítulo o sobre la raíz del
 *  presupuesto ("Arrastrar al presupuesto", Fase 41): analiza cada fichero
 *  igual que la pantalla "Importar BC3" (sin escribir nada) y, si el
 *  usuario confirma, lo cuelga ahí en vez de crear un presupuesto nuevo.
 *  `capituloId: null` significa la raíz. Con más de un fichero, se procesan
 *  de uno en uno — cada uno con su propio análisis y confirmación, para no
 *  colgar nada sin que se haya podido revisar antes. */
export function ImportarBC3EnCapituloModal({
  ficheros,
  presupuestoId,
  capituloResumen,
  capituloId,
  onClose,
  onImportado,
}: {
  ficheros: File[]
  presupuestoId: string
  capituloResumen: string
  capituloId: string | null
  onClose: () => void
  onImportado: () => void
}) {
  const [indice, setIndice] = useState(0)
  const [analisis, setAnalisis] = useState<AnalisisBC3 | null>(null)
  const [estrategia, setEstrategia] = useState<'omitir' | 'actualizar'>('omitir')
  const [analizando, setAnalizando] = useState(true)
  const [importando, setImportando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<ImportacionBC3 | null>(null)

  const fichero = ficheros[indice]
  const varios = ficheros.length > 1
  const quedanMas = indice < ficheros.length - 1

  useEffect(() => {
    let cancelado = false
    setAnalizando(true)
    setAnalisis(null)
    setResultado(null)
    setError(null)
    api.fiebdc
      .analizar(fichero)
      .then((resultado) => {
        if (!cancelado) setAnalisis(resultado)
      })
      .catch((err) => {
        if (!cancelado) setError(err instanceof Error ? err.message : 'Error desconocido')
      })
      .finally(() => {
        if (!cancelado) setAnalizando(false)
      })
    return () => {
      cancelado = true
    }
  }, [fichero, indice])

  async function importar() {
    setImportando(true)
    setError(null)
    try {
      const salida = capituloId
        ? await api.fiebdc.importarEnCapitulo(capituloId, fichero, estrategia)
        : await api.fiebdc.importarEnPresupuesto(presupuestoId, fichero, estrategia)
      setResultado(salida)
      onImportado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setImportando(false)
    }
  }

  return (
    <Modal
      title={
        (capituloId ? 'Importar BC3 en este capítulo' : 'Importar BC3 en la raíz del presupuesto') +
        (varios ? ` (${indice + 1} de ${ficheros.length})` : '')
      }
      onClose={onClose}
    >
      <div className="form-section">
        {!resultado && (
          <p className="form-section__note">
            <strong>{fichero.name}</strong>{' '}
            {capituloId ? (
              <>
                se colgará de <strong>«{capituloResumen}»</strong>, detrás de lo que ya tenga.
              </>
            ) : (
              <>se colgará de la raíz del presupuesto, detrás de los capítulos que ya tenga.</>
            )}
          </p>
        )}

        {analizando && <p className="muted">Analizando el fichero…</p>}

        {analisis && !resultado && (
          <div className="ficha-datos">
            <div>
              <div className="barra-acciones__etiqueta">Programa</div>
              <div className="ficha-datos__valor">{analisis.programa || '—'}</div>
            </div>
            <div>
              <div className="barra-acciones__etiqueta">Conceptos</div>
              <div className="ficha-datos__valor">{analisis.total_conceptos}</div>
            </div>
            <div>
              <div className="barra-acciones__etiqueta">Líneas de descomposición</div>
              <div className="ficha-datos__valor">{analisis.lineas_descomposicion}</div>
            </div>
            <div>
              <div className="barra-acciones__etiqueta">Mediciones</div>
              <div className="ficha-datos__valor">{analisis.mediciones}</div>
            </div>
          </div>
        )}

        {analisis && !analisis.es_presupuesto && !resultado && (
          <p className="notice notice--aviso">
            El fichero no trae estructura de capítulos/partidas, solo conceptos de precio — se
            sumarán al banco de precios, pero no se colgará nada
            {capituloId ? ` de «${capituloResumen}»` : ' de la raíz'}.
          </p>
        )}

        {analisis && analisis.incidencias.length > 0 && !resultado && (
          <details>
            <summary className="muted">{analisis.incidencias.length} incidencia(s) del fichero</summary>
            <ul className="lista-incidencias">
              {analisis.incidencias.slice(0, 20).map((inc, i) => (
                <li key={i}>{inc}</li>
              ))}
            </ul>
          </details>
        )}

        {analisis && !resultado && (
          <label className="field">
            <span className="field__label">Si un código de concepto ya existe en el banco</span>
            <select
              className="select"
              value={estrategia}
              onChange={(e) => setEstrategia(e.target.value as 'omitir' | 'actualizar')}
            >
              <option value="omitir">Respetar lo que ya hay</option>
              <option value="actualizar">Actualizar con lo del fichero</option>
            </select>
          </label>
        )}

        {resultado && (
          <>
            <p className="form-section__note">
              <strong>{fichero.name}</strong> importado
              {capituloId ? (
                <>
                  {' '}
                  en <strong>«{capituloResumen}»</strong>.
                </>
              ) : (
                <> en la raíz del presupuesto.</>
              )}
            </p>
            <div className="ficha-datos">
              <div>
                <div className="barra-acciones__etiqueta">Capítulos añadidos</div>
                <div className="ficha-datos__valor">{resultado.capitulos}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Partidas añadidas</div>
                <div className="ficha-datos__valor">{resultado.partidas}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Líneas de medición</div>
                <div className="ficha-datos__valor">{resultado.lineas_medicion}</div>
              </div>
              <div>
                <div className="barra-acciones__etiqueta">Conceptos al banco</div>
                <div className="ficha-datos__valor">
                  {resultado.conceptos_creados + resultado.conceptos_actualizados}
                </div>
              </div>
            </div>
            {resultado.capitulos === 0 && resultado.partidas === 0 && (
              <p className="notice notice--aviso">
                No se ha colgado ningún capítulo ni partida — mira las incidencias de abajo para
                saber por qué.
              </p>
            )}
            {resultado.incidencias.length > 0 && (
              <details open={resultado.capitulos === 0 && resultado.partidas === 0}>
                <summary className="muted">{resultado.incidencias.length} incidencia(s)</summary>
                <ul className="lista-incidencias">
                  {resultado.incidencias.map((inc, i) => (
                    <li key={i}>{inc}</li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}

        <ErrorNotice error={error} />
      </div>
      <div className="form-actions">
        {resultado ? (
          quedanMas ? (
            <button className="btn btn--primary" onClick={() => setIndice((i) => i + 1)}>
              <ChevronRight size={16} aria-hidden="true" />
              Siguiente fichero
            </button>
          ) : (
            <button className="btn btn--primary" onClick={onClose}>
              <Check size={16} aria-hidden="true" />
              Cerrar
            </button>
          )
        ) : (
          <>
            <button className="btn" onClick={onClose}>
              <X size={16} aria-hidden="true" />
              Cancelar
            </button>
            <button
              className="btn btn--primary"
              disabled={!analisis || importando}
              onClick={() => void importar()}
            >
              {importando ? <FileUp size={16} aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}
              {importando ? 'Importando…' : 'Importar aquí'}
            </button>
          </>
        )}
      </div>
    </Modal>
  )
}
