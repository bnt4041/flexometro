import { useCallback, useEffect, useState } from 'react'

import { DocumentosPRL } from '../components/DocumentosPRL'
import { ErrorNotice, Field, IconButton, Modal } from '../components/ui'
import { api } from '../lib/api'
import type {
  AmbitoPRL,
  EtiquetaPlantilla,
  DatosPlantilla,
  DatosTipoPRL,
  PersonalPRL,
  PlantillaDocumento,
  TipoDocumentoPRL,
} from '../lib/api'
import { SemaforoDocumentos } from './Recursos'

const AMBITOS: { valor: AmbitoPRL; etiqueta: string }[] = [
  { valor: 'empresa', etiqueta: 'Empresa' },
  { valor: 'personal', etiqueta: 'Personal' },
  { valor: 'recurso', etiqueta: 'Recursos' },
  { valor: 'obra', etiqueta: 'Obras' },
  { valor: 'proveedor', etiqueta: 'Proveedores' },
]

const ETIQUETA_AMBITO = Object.fromEntries(AMBITOS.map((a) => [a.valor, a.etiqueta])) as Record<
  AmbitoPRL,
  string
>

type Pestana = 'empresa' | 'personal' | 'catalogo' | 'plantillas'

/** Prevención de riesgos laborales de la organización.
 *
 *  Reúne cuatro cosas que en la práctica se consultan juntas: los papeles de
 *  la propia empresa, el estado de la plantilla, el catálogo de qué se exige
 *  y las plantillas de documento que luego se mandan a firmar. */
export function Prl() {
  const [pestana, setPestana] = useState<Pestana>('empresa')

  return (
    <div>
      <div className="page-head">
        <h1>PRL</h1>
      </div>

      <div className="ficha-pestanas" role="tablist" style={{ marginBottom: 'var(--sp-4)' }}>
        {(
          [
            ['empresa', 'Documentación de empresa'],
            ['personal', 'Vigilancia de la plantilla'],
            ['catalogo', 'Catálogo de documentos'],
            ['plantillas', 'Plantillas'],
          ] as [Pestana, string][]
        ).map(([id, etiqueta]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={pestana === id}
            className={pestana === id ? 'ficha-pestana ficha-pestana--activa' : 'ficha-pestana'}
            onClick={() => setPestana(id)}
          >
            {etiqueta}
          </button>
        ))}
      </div>

      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        {pestana === 'empresa' && (
          <DocumentosPRL ambito="empresa" titulo="Documentación PRL de la empresa" />
        )}
        {pestana === 'personal' && <VigilanciaPersonal />}
        {pestana === 'catalogo' && <Catalogo />}
        {pestana === 'plantillas' && <Plantillas />}
      </div>
    </div>
  )
}

/** Quién tiene qué caducado, de un vistazo. Es la pregunta que se hace antes
 *  de una visita de la inspección o al mandar gente a una obra nueva. */
function VigilanciaPersonal() {
  const [personas, setPersonas] = useState<PersonalPRL[]>([])
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  useEffect(() => {
    api.prl
      .personal(true)
      .then(setPersonas)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
      .finally(() => setCargando(false))
  }, [])

  const hoy = new Date().toISOString().slice(0, 10)

  if (cargando) return <p className="muted">Cargando…</p>
  return (
    <div>
      <ErrorNotice error={error} />
      {personas.length === 0 ? (
        <p className="muted">No hay personal activo.</p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Trabajador</th>
                <th>Categoría</th>
                <th>Formación PRL</th>
                <th>Reconocimiento</th>
                <th>TPC</th>
                <th>Documentación</th>
              </tr>
            </thead>
            <tbody>
              {personas.map((persona) => (
                <tr key={persona.id}>
                  <td>
                    {persona.nombre} {persona.apellidos ?? ''}
                    {persona.es_recurso_preventivo && (
                      <div className="muted" style={{ fontSize: '0.85em' }}>
                        Recurso preventivo
                      </div>
                    )}
                  </td>
                  <td>{persona.categoria ?? '—'}</td>
                  <td>
                    {persona.formacion_prl_horas ? (
                      `${persona.formacion_prl_horas} h`
                    ) : (
                      <span className="notice notice--aviso" style={{ margin: 0, padding: '2px 8px' }}>
                        Sin registrar
                      </span>
                    )}
                  </td>
                  <td>
                    <Caducidad fecha={persona.proximo_reconocimiento} hoy={hoy} />
                  </td>
                  <td>
                    <Caducidad fecha={persona.tpc_caducidad} hoy={hoy} />
                  </td>
                  <td>
                    <SemaforoDocumentos
                      caducados={persona.documentos_caducados}
                      porCaducar={persona.documentos_por_caducar}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Caducidad({ fecha, hoy }: { fecha: string | null; hoy: string }) {
  if (!fecha) return <span className="muted">—</span>
  if (fecha < hoy) {
    return (
      <span className="notice notice--error" style={{ margin: 0, padding: '2px 8px' }}>
        Vencido {fecha}
      </span>
    )
  }
  return <>{fecha}</>
}

/** Qué documentos se exigen y cuánto duran. Es dato editable, no código: la
 *  norma cambia y cada empresa tiene sus propias exigencias. */
function Catalogo() {
  const [tipos, setTipos] = useState<TipoDocumentoPRL[]>([])
  const [error, setError] = useState<string | null>(null)
  const [modal, setModal] = useState(false)
  const [datos, setDatos] = useState<DatosTipoPRL>({
    nombre: '',
    ambito: 'empresa',
    meses_validez: 12,
    obligatorio: false,
  })

  const cargar = useCallback(async () => {
    try {
      setTipos(await api.prl.tipos.list({ solo_activos: false }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function guardar() {
    if (!datos.nombre.trim()) {
      setError('El nombre es obligatorio.')
      return
    }
    try {
      await api.prl.tipos.create(datos)
      setModal(false)
      setDatos({ nombre: '', ambito: 'empresa', meses_validez: 12, obligatorio: false })
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--sp-3)' }}>
        <div className="form-section__title" style={{ margin: 0 }}>
          Catálogo de documentos exigibles
        </div>
        <IconButton icono="nuevo" texto="Nuevo tipo" variante="primary" onClick={() => setModal(true)} />
      </div>
      <ErrorNotice error={error} />
      <div style={{ overflowX: 'auto' }}>
        <table className="table">
          <thead>
            <tr>
              <th>Documento</th>
              <th>Ámbito</th>
              <th>Validez</th>
              <th>Obligatorio</th>
            </tr>
          </thead>
          <tbody>
            {tipos.map((tipo) => (
              <tr key={tipo.id} style={{ opacity: tipo.activo ? 1 : 0.5 }}>
                <td>{tipo.nombre}</td>
                <td>{ETIQUETA_AMBITO[tipo.ambito]}</td>
                <td>{tipo.meses_validez > 0 ? `${tipo.meses_validez} meses` : 'No caduca'}</td>
                <td>{tipo.obligatorio ? 'Sí' : 'No'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal title="Nuevo tipo de documento" onClose={() => setModal(false)}>
          <div className="form-section">
            <ErrorNotice error={error} />
            <div className="form-grid">
              <Field ancho="doble" label="Nombre">
                <input
                  className="input"
                  value={datos.nombre}
                  onChange={(e) => setDatos({ ...datos, nombre: e.target.value })}
                />
              </Field>
              <Field label="Ámbito">
                <select
                  className="input"
                  value={datos.ambito}
                  onChange={(e) => setDatos({ ...datos, ambito: e.target.value as AmbitoPRL })}
                >
                  {AMBITOS.map((a) => (
                    <option key={a.valor} value={a.valor}>
                      {a.etiqueta}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Validez (meses)" hint="0 = no caduca">
                <input
                  className="input"
                  type="number"
                  min={0}
                  value={datos.meses_validez ?? 12}
                  onChange={(e) => setDatos({ ...datos, meses_validez: Number(e.target.value) })}
                />
              </Field>
              <Field ancho="doble" label="Obligatorio">
                <label style={{ display: 'inline-flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
                  <input
                    type="checkbox"
                    checked={datos.obligatorio ?? false}
                    onChange={(e) => setDatos({ ...datos, obligatorio: e.target.checked })}
                  />
                  Se avisa si falta
                </label>
              </Field>
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={() => setModal(false)}>
              Cancelar
            </button>
            <button type="button" className="btn btn--primary" onClick={guardar}>
              Crear
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

/** Patrones de documento reutilizables. El contenido admite marcadores que se
 *  sustituyen al generar cada envío. */
function Plantillas() {
  const [plantillas, setPlantillas] = useState<PlantillaDocumento[]>([])
  const [etiquetas, setEtiquetas] = useState<EtiquetaPlantilla[]>([])
  const [error, setError] = useState<string | null>(null)
  const [editando, setEditando] = useState<PlantillaDocumento | null>(null)
  const [modal, setModal] = useState(false)
  const [datos, setDatos] = useState<DatosPlantilla>({
    nombre: '',
    ambito: 'proveedor',
    contenido: '',
    requiere_firma: true,
  })

  const cargar = useCallback(async () => {
    try {
      setPlantillas(await api.prl.plantillas.list({}))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [])

  useEffect(() => {
    void cargar()
    // Las etiquetas vienen del servidor, no escritas aquí a mano: así no
    // pueden quedar desfasadas respecto a lo que se sustituye de verdad.
    api.prl.plantillas.etiquetas().then(setEtiquetas).catch(() => setEtiquetas([]))
  }, [cargar])

  function abrir(plantilla?: PlantillaDocumento) {
    setEditando(plantilla ?? null)
    setDatos(
      plantilla
        ? {
            nombre: plantilla.nombre,
            ambito: plantilla.ambito,
            contenido: plantilla.contenido,
            requiere_firma: plantilla.requiere_firma,
            activa: plantilla.activa,
          }
        : { nombre: '', ambito: 'proveedor', contenido: '', requiere_firma: true },
    )
    setError(null)
    setModal(true)
  }

  async function guardar() {
    if (!datos.nombre.trim()) {
      setError('El nombre es obligatorio.')
      return
    }
    try {
      if (editando) await api.prl.plantillas.update(editando.id, datos)
      else await api.prl.plantillas.create(datos)
      setModal(false)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--sp-3)' }}>
        <div className="form-section__title" style={{ margin: 0 }}>
          Plantillas de documento
        </div>
        <IconButton icono="nuevo" texto="Nueva plantilla" variante="primary" onClick={() => abrir()} />
      </div>
      <ErrorNotice error={error} />
      {plantillas.length === 0 ? (
        <p className="muted">
          Todavía no hay plantillas. Sirven para no reescribir cada vez un acta de coordinación o un
          acuse de entrega antes de mandarlo a firmar.
        </p>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Ámbito</th>
                <th>Requiere firma</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {plantillas.map((plantilla) => (
                <tr key={plantilla.id} style={{ opacity: plantilla.activa ? 1 : 0.5 }}>
                  <td>{plantilla.nombre}</td>
                  <td>{ETIQUETA_AMBITO[plantilla.ambito]}</td>
                  <td>{plantilla.requiere_firma ? 'Sí' : 'No'}</td>
                  <td style={{ textAlign: 'right' }}>
                    <IconButton
                      icono="editar"
                      texto="Editar"
                      soloIcono
                      tamano="sm"
                      onClick={() => abrir(plantilla)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {modal && (
        <Modal title={editando ? 'Editar plantilla' : 'Nueva plantilla'} onClose={() => setModal(false)}>
          <div className="form-section">
            <ErrorNotice error={error} />
            <div className="form-grid">
              <Field ancho="doble" label="Nombre">
                <input
                  className="input"
                  value={datos.nombre}
                  onChange={(e) => setDatos({ ...datos, nombre: e.target.value })}
                />
              </Field>
              <Field label="Ámbito">
                <select
                  className="input"
                  value={datos.ambito}
                  onChange={(e) => setDatos({ ...datos, ambito: e.target.value as AmbitoPRL })}
                >
                  {AMBITOS.map((a) => (
                    <option key={a.valor} value={a.valor}>
                      {a.etiqueta}
                    </option>
                  ))}
                </select>
              </Field>
              <Field ancho="completo" label="Contenido">
                <textarea
                  className="input"
                  rows={12}
                  value={datos.contenido ?? ''}
                  onChange={(e) => setDatos({ ...datos, contenido: e.target.value })}
                  placeholder="<p>Por la presente se hace entrega a {{destinatario}} de…</p>"
                />
                <AyudaEtiquetas
                  etiquetas={etiquetas}
                  onInsertar={(etiqueta) =>
                    setDatos((previo) => ({
                      ...previo,
                      contenido: (previo.contenido ?? '') + etiqueta,
                    }))
                  }
                />
              </Field>
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={() => setModal(false)}>
              Cancelar
            </button>
            <button type="button" className="btn btn--primary" onClick={guardar}>
              Guardar
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}


/** Chuleta de marcadores disponibles al escribir una plantilla.
 *
 *  Se pintan como botones y no como texto de ayuda porque lo que de verdad
 *  hace falta es METERLOS en el contenido sin equivocarse al teclear las
 *  llaves: un `{destinatario}` con una sola llave no falla, simplemente sale
 *  literal en el documento firmado, y eso no se descubre hasta que el
 *  proveedor lo recibe. */
function AyudaEtiquetas({
  etiquetas,
  onInsertar,
}: {
  etiquetas: EtiquetaPlantilla[]
  onInsertar: (etiqueta: string) => void
}) {
  if (etiquetas.length === 0) return null
  return (
    <div
      style={{
        marginTop: 'var(--sp-3)',
        padding: 'var(--sp-3)',
        border: '1px solid var(--c-border)',
        borderRadius: 'var(--radius)',
        background: 'var(--c-surface-2)',
      }}
    >
      <div style={{ fontWeight: 600, fontSize: '0.85em', marginBottom: 'var(--sp-2)' }}>
        Etiquetas disponibles
      </div>
      <p className="muted" style={{ fontSize: '0.85em', margin: '0 0 var(--sp-3)' }}>
        Se sustituyen por el dato real al crear cada solicitud de firma. Pulsa una para añadirla al
        final del contenido.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
        {etiquetas.map((e) => (
          <div
            key={e.etiqueta}
            style={{ display: 'flex', gap: 'var(--sp-3)', alignItems: 'baseline', flexWrap: 'wrap' }}
          >
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => onInsertar(e.etiqueta)}
              style={{ fontFamily: 'monospace' }}
            >
              {e.etiqueta}
            </button>
            <span className="muted" style={{ fontSize: '0.85em' }}>
              {e.descripcion} — p. ej. <em>{e.ejemplo}</em>
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
