import { useEffect, useState } from 'react'
import { Upload, X } from 'lucide-react'

import { ErrorNotice, Field, Modal } from './ui'
import { api } from '../lib/api'
import type { AnalisisBC3, ImportacionBC3 } from '../lib/api'

/** Importar uno o varios BC3 al banco de precios (Fase 50) — se llega aquí
 *  soltando el fichero sobre la rejilla. A diferencia del importador de
 *  presupuestos, aquí NUNCA se crea un presupuesto: solo suben las fichas y
 *  sus descompuestos, al capítulo sobre el que se soltó.
 *
 *  Primero se analiza (sin escribir nada) para poder enseñar qué trae el
 *  fichero antes de tocar el banco — un BEDEC entero son decenas de miles de
 *  fichas y conviene saberlo antes de darle a importar. */
export function ImportarBancoModal({
  ficheros,
  capituloId,
  onClose,
  onImportado,
}: {
  ficheros: File[]
  capituloId: string | null
  onClose: () => void
  onImportado: () => void
}) {
  const [analisis, setAnalisis] = useState<(AnalisisBC3 | null)[]>([])
  const [estrategia, setEstrategia] = useState('omitir')
  const [resultado, setResultado] = useState<ImportacionBC3[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [trabajando, setTrabajando] = useState(true)

  useEffect(() => {
    let cancelado = false
    void (async () => {
      try {
        const analizados = await Promise.all(
          ficheros.map((f) => api.fiebdc.analizar(f).catch(() => null)),
        )
        if (!cancelado) setAnalisis(analizados)
      } finally {
        if (!cancelado) setTrabajando(false)
      }
    })()
    return () => {
      cancelado = true
    }
  }, [ficheros])

  async function importar() {
    setTrabajando(true)
    setError(null)
    try {
      const resultados: ImportacionBC3[] = []
      // Uno a uno: un BC3 grande tarda, y en tanda paralela no se sabría
      // cuál de ellos falló.
      for (const fichero of ficheros) {
        resultados.push(
          await api.fiebdc.importar(fichero, {
            estrategia,
            crear_presupuesto: false,
            capitulo_banco_id: capituloId,
          }),
        )
      }
      setResultado(resultados)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setTrabajando(false)
    }
  }

  const totales = resultado?.reduce(
    (acc, r) => ({
      creados: acc.creados + r.conceptos_creados,
      actualizados: acc.actualizados + r.conceptos_actualizados,
      omitidos: acc.omitidos + r.conceptos_omitidos,
      lineas: acc.lineas + r.lineas_descomposicion,
    }),
    { creados: 0, actualizados: 0, omitidos: 0, lineas: 0 },
  )

  return (
    <Modal title="Importar al banco de precios" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />

        {totales ? (
          <div className="notice notice--ok">
            {totales.creados} fichas nuevas, {totales.actualizados} actualizadas,{' '}
            {totales.omitidos} sin tocar y {totales.lineas} líneas de descompuesto.
            {capituloId && ' Se han colocado en el capítulo elegido.'}
          </div>
        ) : (
          <>
            <p className="form-section__note">
              {capituloId
                ? 'Las fichas del fichero se colocarán en el capítulo sobre el que has soltado.'
                : 'Las fichas del fichero se colocarán en la raíz del banco.'}
            </p>

            <div className="table-wrap" style={{ marginBottom: 'var(--sp-4)' }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>Fichero</th>
                    <th className="table__num">Fichas</th>
                    <th className="table__num">Descompuestos</th>
                  </tr>
                </thead>
                <tbody>
                  {ficheros.map((f, i) => (
                    <tr key={f.name}>
                      <td>{f.name}</td>
                      <td className="table__num">
                        {analisis[i] ? analisis[i]!.total_conceptos : '—'}
                      </td>
                      <td className="table__num">
                        {analisis[i] ? analisis[i]!.lineas_descomposicion : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Field
              label="Si el código ya existe"
              hint="Los códigos del banco son únicos: hay que decidir qué hacer cuando el fichero trae uno repetido"
            >
              <select
                className="select"
                value={estrategia}
                onChange={(e) => setEstrategia(e.target.value)}
              >
                <option value="omitir">Dejar la ficha que ya tengo</option>
                <option value="actualizar">Actualizarla con la del fichero</option>
              </select>
            </Field>
          </>
        )}
      </div>

      <div className="form-actions">
        <button className="btn" onClick={totales ? onImportado : onClose}>
          <X size={16} aria-hidden="true" />
          {totales ? 'Cerrar' : 'Cancelar'}
        </button>
        {!totales && (
          <button className="btn btn--primary" disabled={trabajando} onClick={() => void importar()}>
            <Upload size={16} aria-hidden="true" />
            {trabajando ? 'Trabajando…' : 'Importar'}
          </button>
        )}
      </div>
    </Modal>
  )
}
