import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, Upload } from 'lucide-react'

import { ErrorNotice, Field, IconButton, Modal } from './ui'
import { api, descargar } from '../lib/api'
import { useWorkspace } from '../workspace'
import type {
  AmbitoPRL,
  DatosDocumentoPRL,
  DocumentoPRL,
  EntidadDocumento,
  EstadoVigencia,
  ResumenVigencia,
  TipoDocumentoPRL,
} from '../lib/api'

/** El mismo bloque de documentos PRL sirve para los cuatro ámbitos con
 *  entidad (obra, personal, recurso, proveedor) y para la empresa, que no
 *  tiene ninguna. Es idéntico en todos: un tipo del catálogo, una fecha de
 *  caducidad y un fichero — lo único que cambia es a qué cuelga. */
const ENTIDAD_DOCUMENTO: Record<AmbitoPRL, EntidadDocumento> = {
  empresa: 'prl_empresa',
  personal: 'personal',
  recurso: 'recurso',
  obra: 'obra',
  proveedor: 'tercero',
}

const ETIQUETA_ESTADO: Record<EstadoVigencia, string> = {
  vigente: 'Vigente',
  por_caducar: 'Por caducar',
  caducado: 'Caducado',
  pendiente: 'Sin aportar',
}

/** Color por estado. Rojo y ámbar se distinguen también por el TEXTO de la
 *  etiqueta, no solo por el color: el semáforo tiene que leerse igual con
 *  daltonismo rojo-verde, que es lo que ya vigila `tokens.css`. */
const CLASE_ESTADO: Record<EstadoVigencia, string> = {
  vigente: 'notice--ok',
  por_caducar: 'notice--aviso',
  caducado: 'notice--error',
  pendiente: 'notice--aviso',
}

function hoyISO(): string {
  return new Date().toISOString().slice(0, 10)
}

/** Caducidad propuesta = hoy + los meses de validez del tipo. Réplica de
 *  `caducidad_sugerida` del backend, solo para rellenar el formulario: la
 *  fecha que vale es la que el usuario confirme. */
function caducidadSugerida(emision: string, meses: number): string {
  const base = emision ? new Date(emision) : new Date()
  if (meses <= 0) return `${base.getFullYear() + 99}-${String(base.getMonth() + 1).padStart(2, '0')}-${String(base.getDate()).padStart(2, '0')}`
  const destino = new Date(base)
  destino.setMonth(destino.getMonth() + meses)
  // `setMonth` desborda al mes siguiente si el día no existe (31 de enero + 1
  // mes daría 3 de marzo): se recorta al último día del mes destino.
  if (destino.getDate() !== base.getDate()) destino.setDate(0)
  return destino.toISOString().slice(0, 10)
}

export function DocumentosPRL({
  ambito,
  entidadId,
  titulo = 'Documentación PRL',
}: {
  ambito: AmbitoPRL
  /** Vacío solo cuando `ambito` es "empresa". */
  entidadId?: string
  titulo?: string
}) {
  const { principal } = useWorkspace()
  const [documentos, setDocumentos] = useState<DocumentoPRL[]>([])
  const [resumen, setResumen] = useState<ResumenVigencia | null>(null)
  const [tipos, setTipos] = useState<TipoDocumentoPRL[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [modal, setModal] = useState(false)
  const [guardando, setGuardando] = useState(false)
  const ficheroRef = useRef<HTMLInputElement>(null)

  const [tipoId, setTipoId] = useState('')
  const [emision, setEmision] = useState(hoyISO())
  const [caducidad, setCaducidad] = useState('')
  const [notas, setNotas] = useState('')

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const [docs, res, cat] = await Promise.all([
        api.prl.documentos.list({ ambito, entidad_id: entidadId }),
        api.prl.documentos.resumen({ ambito, entidad_id: entidadId }),
        api.prl.tipos.list({ ambito }),
      ])
      setDocumentos(docs)
      setResumen(res)
      setTipos(cat)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [ambito, entidadId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const tipoElegido = useMemo(() => tipos.find((t) => t.id === tipoId), [tipos, tipoId])

  function abrir() {
    setTipoId('')
    setEmision(hoyISO())
    setCaducidad('')
    setNotas('')
    setError(null)
    setModal(true)
  }

  function elegirTipo(id: string) {
    setTipoId(id)
    const tipo = tipos.find((t) => t.id === id)
    if (tipo) setCaducidad(caducidadSugerida(emision, tipo.meses_validez))
  }

  function cambiarEmision(valor: string) {
    setEmision(valor)
    if (tipoElegido) setCaducidad(caducidadSugerida(valor, tipoElegido.meses_validez))
  }

  async function guardar() {
    if (!tipoId || !caducidad) {
      setError('Hacen falta el tipo de documento y la fecha de caducidad.')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      // El fichero es opcional: registrar que un documento FALTA, con su
      // fecha límite, es tan útil como registrar que se tiene.
      let documentoId: string | null = null
      const fichero = ficheroRef.current?.files?.[0]
      if (fichero) {
        // Los documentos de ámbito EMPRESA no cuelgan de ninguna ficha, pero
        // el gestor documental exige una entidad: se usa la propia
        // organización, que es literalmente de quien son esos papeles.
        const destino = entidadId ?? principal?.organization_id
        if (!destino) throw new Error('No se ha podido determinar la organización activa')
        const subido = await api.documentos.upload(ENTIDAD_DOCUMENTO[ambito], destino, fichero)
        documentoId = subido.id
      }
      const datos: DatosDocumentoPRL = {
        tipo_id: tipoId,
        ambito,
        entidad_id: entidadId ?? null,
        fecha_emision: emision || null,
        fecha_caducidad: caducidad,
        documento_id: documentoId,
        notas: notas || null,
      }
      await api.prl.documentos.create(datos)
      setModal(false)
      if (ficheroRef.current) ficheroRef.current.value = ''
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function borrar(id: string) {
    try {
      await api.prl.documentos.remove(id)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 'var(--sp-3)',
          gap: 'var(--sp-3)',
          flexWrap: 'wrap',
        }}
      >
        <div className="form-section__title" style={{ margin: 0 }}>
          {titulo}
        </div>
        <IconButton icono="nuevo" texto="Añadir documento" variante="primary" onClick={abrir} />
      </div>

      <ErrorNotice error={error} />

      {resumen && resumen.total > 0 && (
        <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap', marginBottom: 'var(--sp-3)' }}>
          <Contador etiqueta="Vigentes" valor={resumen.vigentes} clase="notice--ok" />
          <Contador etiqueta="Por caducar" valor={resumen.por_caducar} clase="notice--aviso" />
          <Contador etiqueta="Caducados" valor={resumen.caducados} clase="notice--error" />
          <Contador etiqueta="Sin aportar" valor={resumen.pendientes} clase="notice--aviso" />
        </div>
      )}

      {resumen && resumen.faltan_obligatorios.length > 0 && (
        <p className="notice notice--aviso">
          <strong>Faltan documentos obligatorios:</strong>{' '}
          {resumen.faltan_obligatorios.join(', ')}.
        </p>
      )}

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : documentos.length === 0 ? (
        <p className="muted">Todavía no hay documentos registrados.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Documento</th>
                <th>Emisión</th>
                <th>Caduca</th>
                <th>Estado</th>
                <th>Fichero</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {documentos.map((documento) => (
                <tr key={documento.id}>
                  <td>
                    {documento.tipo_nombre}
                    {documento.notas && (
                      <div className="muted" style={{ fontSize: '0.85em' }}>
                        {documento.notas}
                      </div>
                    )}
                  </td>
                  <td>{documento.fecha_emision ?? '—'}</td>
                  <td>
                    {documento.fecha_caducidad}
                    {documento.dias_para_caducar !== null && documento.dias_para_caducar >= 0 && (
                      <div className="muted" style={{ fontSize: '0.85em' }}>
                        en {documento.dias_para_caducar} día(s)
                      </div>
                    )}
                  </td>
                  <td>
                    {documento.estado && (
                      <span
                        className={`notice ${CLASE_ESTADO[documento.estado]}`}
                        style={{ padding: '2px 8px', margin: 0, display: 'inline-block' }}
                      >
                        {ETIQUETA_ESTADO[documento.estado]}
                      </span>
                    )}
                  </td>
                  <td>
                    {documento.documento_id ? (
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() =>
                          void descargar(
                            api.documentos.descargarUrl(documento.documento_id!),
                            documento.nombre_archivo ?? 'documento',
                          )
                        }
                      >
                        <Download size={14} aria-hidden="true" /> {documento.nombre_archivo}
                      </button>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <IconButton
                      icono="eliminar"
                      texto="Eliminar"
                      soloIcono
                      variante="danger"
                      tamano="sm"
                      onClick={() => borrar(documento.id)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal && (
        <Modal title="Añadir documento PRL" onClose={() => setModal(false)}>
          <div className="form-section">
            <ErrorNotice error={error} />
            <div className="form-grid">
              <Field ancho="doble" label="Tipo de documento">
                <select className="input" value={tipoId} onChange={(e) => elegirTipo(e.target.value)}>
                  <option value="">Selecciona…</option>
                  {tipos.map((tipo) => (
                    <option key={tipo.id} value={tipo.id}>
                      {tipo.nombre}
                      {tipo.obligatorio ? ' (obligatorio)' : ''}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Fecha de emisión">
                <input
                  className="input"
                  type="date"
                  value={emision}
                  onChange={(e) => cambiarEmision(e.target.value)}
                />
              </Field>
              <Field
                label="Caduca el"
                hint={
                  tipoElegido
                    ? `Propuesta: ${tipoElegido.meses_validez} meses de validez`
                    : undefined
                }
              >
                <input
                  className="input"
                  type="date"
                  value={caducidad}
                  onChange={(e) => setCaducidad(e.target.value)}
                />
              </Field>
              <Field ancho="doble" label="Fichero" hint="Opcional: se puede registrar el documento como pendiente">
                <input className="input" type="file" ref={ficheroRef} />
              </Field>
              <Field ancho="doble" label="Notas">
                <input className="input" value={notas} onChange={(e) => setNotas(e.target.value)} />
              </Field>
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={() => setModal(false)}>
              Cancelar
            </button>
            <button type="button" className="btn btn--primary" onClick={guardar} disabled={guardando}>
              <Upload size={16} aria-hidden="true" /> {guardando ? 'Guardando…' : 'Guardar'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

function Contador({ etiqueta, valor, clase }: { etiqueta: string; valor: number; clase: string }) {
  if (valor === 0) return null
  return (
    <span className={`notice ${clase}`} style={{ margin: 0, padding: '4px 10px' }}>
      <strong>{valor}</strong> {etiqueta}
    </span>
  )
}
