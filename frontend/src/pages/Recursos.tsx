import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { DocumentosPRL } from '../components/DocumentosPRL'
import { EmptyState, ErrorNotice, Field, IconButton, Modal, Pager } from '../components/ui'
import { api } from '../lib/api'
import type { DatosRecurso, Recurso, TipoRecurso } from '../lib/api'

const TIPOS: { valor: TipoRecurso; etiqueta: string }[] = [
  { valor: 'vehiculo', etiqueta: 'Vehículo' },
  { valor: 'maquinaria', etiqueta: 'Maquinaria' },
  { valor: 'herramienta', etiqueta: 'Herramienta' },
  { valor: 'epi', etiqueta: 'EPI' },
  { valor: 'otro', etiqueta: 'Otro' },
]

const ETIQUETA_TIPO = Object.fromEntries(TIPOS.map((t) => [t.valor, t.etiqueta])) as Record<
  TipoRecurso,
  string
>

const VACIO: DatosRecurso = {
  nombre: '',
  tipo: 'maquinaria',
  marca: '',
  modelo: '',
  matricula: '',
  numero_serie: '',
  anio_fabricacion: null,
  fecha_adquisicion: null,
  activo: true,
  notas: '',
}

/** Vehículos, maquinaria y equipos. Vive en "Organización" y no en "Obras"
 *  porque un camión es de la empresa, no de una obra — aunque esté asignado a
 *  una ahora mismo. Lo que de verdad justifica la pantalla es la columna de
 *  documentación: la ITV y el seguro caducan igual que la formación de una
 *  persona, y hasta ahora no había dónde controlarlo. */
export function Recursos() {
  const navegar = useNavigate()
  const [recursos, setRecursos] = useState<Recurso[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [tipo, setTipo] = useState<TipoRecurso | ''>('')
  const [busqueda, setBusqueda] = useState('')
  const [soloActivos, setSoloActivos] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [modal, setModal] = useState(false)
  const [datos, setDatos] = useState<DatosRecurso>(VACIO)
  const [guardando, setGuardando] = useState(false)

  const limite = 25

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const pagina = await api.prl.recursos.list({
        tipo: tipo || undefined,
        q: busqueda || undefined,
        solo_activos: soloActivos,
        limit: limite,
        offset,
      })
      setRecursos(pagina.items)
      setTotal(pagina.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [tipo, busqueda, soloActivos, offset])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function guardar() {
    if (!datos.nombre.trim()) {
      setError('El nombre es obligatorio.')
      return
    }
    setGuardando(true)
    setError(null)
    try {
      await api.prl.recursos.create(datos)
      setModal(false)
      setDatos(VACIO)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Recursos</h1>
        <IconButton
          icono="nuevo"
          texto="Nuevo recurso"
          variante="primary"
          onClick={() => {
            setDatos(VACIO)
            setError(null)
            setModal(true)
          }}
        />
      </div>

      <ErrorNotice error={error} />

      <div className="toolbar" style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          className="input"
          placeholder="Buscar por nombre, matrícula o código…"
          value={busqueda}
          onChange={(e) => {
            setBusqueda(e.target.value)
            setOffset(0)
          }}
          style={{ maxWidth: 320 }}
        />
        <select
          className="input"
          value={tipo}
          onChange={(e) => {
            setTipo(e.target.value as TipoRecurso | '')
            setOffset(0)
          }}
          style={{ maxWidth: 180 }}
        >
          <option value="">Todos los tipos</option>
          {TIPOS.map((t) => (
            <option key={t.valor} value={t.valor}>
              {t.etiqueta}
            </option>
          ))}
        </select>
        <label style={{ display: 'inline-flex', gap: 'var(--sp-2)', alignItems: 'center' }}>
          <input
            type="checkbox"
            checked={soloActivos}
            onChange={(e) => {
              setSoloActivos(e.target.checked)
              setOffset(0)
            }}
          />
          Solo activos
        </label>
      </div>

      {cargando ? (
        <p className="muted">Cargando…</p>
      ) : recursos.length === 0 ? (
        <EmptyState title="Sin recursos">
          Da de alta vehículos, maquinaria o equipos para llevar su documentación y sus caducidades.
        </EmptyState>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Tipo</th>
                <th>Matrícula / serie</th>
                <th>Documentación</th>
              </tr>
            </thead>
            <tbody>
              {recursos.map((recurso) => (
                <tr
                  key={recurso.id}
                  onClick={() => navegar(`/recursos/${recurso.id}`)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{recurso.codigo}</td>
                  <td>
                    {recurso.nombre}
                    {(recurso.marca || recurso.modelo) && (
                      <div className="muted" style={{ fontSize: '0.85em' }}>
                        {[recurso.marca, recurso.modelo].filter(Boolean).join(' ')}
                      </div>
                    )}
                  </td>
                  <td>{ETIQUETA_TIPO[recurso.tipo]}</td>
                  <td>{recurso.matricula || recurso.numero_serie || '—'}</td>
                  <td>
                    <SemaforoDocumentos
                      caducados={recurso.documentos_caducados}
                      porCaducar={recurso.documentos_por_caducar}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pager total={total} limit={limite} offset={offset} onChange={setOffset} />

      {modal && (
        <Modal title="Nuevo recurso" onClose={() => setModal(false)}>
          <div className="form-section">
            <ErrorNotice error={error} />
            <FormularioRecurso datos={datos} onCambio={setDatos} />
          </div>
          <div className="form-actions">
            <button type="button" className="btn" onClick={() => setModal(false)}>
              Cancelar
            </button>
            <button type="button" className="btn btn--primary" onClick={guardar} disabled={guardando}>
              {guardando ? 'Guardando…' : 'Crear'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}

/** Un recurso sin papeles caducados no necesita adorno: solo se pinta cuando
 *  hay algo que mirar, para que la columna sea escaneable de un vistazo. */
export function SemaforoDocumentos({
  caducados,
  porCaducar,
}: {
  caducados: number
  porCaducar: number
}) {
  if (caducados === 0 && porCaducar === 0) return <span className="muted">Al día</span>
  return (
    <span style={{ display: 'inline-flex', gap: 'var(--sp-2)' }}>
      {caducados > 0 && (
        <span className="notice notice--error" style={{ margin: 0, padding: '2px 8px' }}>
          {caducados} caducado(s)
        </span>
      )}
      {porCaducar > 0 && (
        <span className="notice notice--aviso" style={{ margin: 0, padding: '2px 8px' }}>
          {porCaducar} por caducar
        </span>
      )}
    </span>
  )
}

function FormularioRecurso({
  datos,
  onCambio,
}: {
  datos: DatosRecurso
  onCambio: (datos: DatosRecurso) => void
}) {
  const set = <K extends keyof DatosRecurso>(campo: K, valor: DatosRecurso[K]) =>
    onCambio({ ...datos, [campo]: valor })

  return (
    <div className="form-grid">
      <Field ancho="doble" label="Nombre">
        <input className="input" value={datos.nombre} onChange={(e) => set('nombre', e.target.value)} />
      </Field>
      <Field label="Tipo">
        <select
          className="input"
          value={datos.tipo}
          onChange={(e) => set('tipo', e.target.value as TipoRecurso)}
        >
          {TIPOS.map((t) => (
            <option key={t.valor} value={t.valor}>
              {t.etiqueta}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Marca">
        <input className="input" value={datos.marca ?? ''} onChange={(e) => set('marca', e.target.value)} />
      </Field>
      <Field label="Modelo">
        <input className="input" value={datos.modelo ?? ''} onChange={(e) => set('modelo', e.target.value)} />
      </Field>
      <Field label="Matrícula">
        <input
          className="input"
          value={datos.matricula ?? ''}
          onChange={(e) => set('matricula', e.target.value)}
        />
      </Field>
      <Field label="Número de serie">
        <input
          className="input"
          value={datos.numero_serie ?? ''}
          onChange={(e) => set('numero_serie', e.target.value)}
        />
      </Field>
      <Field label="Año de fabricación">
        <input
          className="input"
          type="number"
          value={datos.anio_fabricacion ?? ''}
          onChange={(e) => set('anio_fabricacion', e.target.value ? Number(e.target.value) : null)}
        />
      </Field>
      <Field label="Fecha de adquisición">
        <input
          className="input"
          type="date"
          value={datos.fecha_adquisicion ?? ''}
          onChange={(e) => set('fecha_adquisicion', e.target.value || null)}
        />
      </Field>
      <Field ancho="completo" label="Notas">
        <input className="input" value={datos.notas ?? ''} onChange={(e) => set('notas', e.target.value)} />
      </Field>
    </div>
  )
}

/** Ficha del recurso: sus datos y, sobre todo, su documentación PRL. */
export function RecursoDetalle() {
  const { id = '' } = useParams()
  const navegar = useNavigate()
  const [recurso, setRecurso] = useState<Recurso | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editando, setEditando] = useState(false)
  const [datos, setDatos] = useState<DatosRecurso>(VACIO)

  const cargar = useCallback(async () => {
    try {
      const encontrado = await api.prl.recursos.get(id)
      setRecurso(encontrado)
      setDatos({
        nombre: encontrado.nombre,
        tipo: encontrado.tipo,
        marca: encontrado.marca,
        modelo: encontrado.modelo,
        matricula: encontrado.matricula,
        numero_serie: encontrado.numero_serie,
        anio_fabricacion: encontrado.anio_fabricacion,
        fecha_adquisicion: encontrado.fecha_adquisicion,
        activo: encontrado.activo,
        notas: encontrado.notas,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  async function guardar() {
    try {
      await api.prl.recursos.update(id, datos)
      setEditando(false)
      await cargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  if (!recurso) return <ErrorNotice error={error} />

  return (
    <div>
      <div className="page-head">
        <h1>
          {recurso.codigo} · {recurso.nombre}
        </h1>
        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
          <button type="button" className="btn" onClick={() => navegar('/recursos')}>
            Volver
          </button>
          <IconButton
            icono={editando ? 'guardar' : 'editar'}
            texto={editando ? 'Guardar' : 'Editar'}
            variante="primary"
            onClick={() => (editando ? guardar() : setEditando(true))}
          />
        </div>
      </div>

      <ErrorNotice error={error} />

      <div className="card" style={{ padding: 'var(--sp-5)', marginBottom: 'var(--sp-5)' }}>
        {editando ? (
          <FormularioRecurso datos={datos} onCambio={setDatos} />
        ) : (
          <div className="form-grid">
            <Dato etiqueta="Tipo" valor={ETIQUETA_TIPO[recurso.tipo]} />
            <Dato etiqueta="Marca" valor={recurso.marca} />
            <Dato etiqueta="Modelo" valor={recurso.modelo} />
            <Dato etiqueta="Matrícula" valor={recurso.matricula} />
            <Dato etiqueta="Nº de serie" valor={recurso.numero_serie} />
            <Dato etiqueta="Año" valor={recurso.anio_fabricacion?.toString()} />
            <Dato etiqueta="Adquisición" valor={recurso.fecha_adquisicion} />
            <Dato etiqueta="Estado" valor={recurso.activo ? 'Activo' : 'De baja'} />
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 'var(--sp-5)' }}>
        <DocumentosPRL ambito="recurso" entidadId={id} />
      </div>
    </div>
  )
}

function Dato({ etiqueta, valor }: { etiqueta: string; valor?: string | null }) {
  return (
    <div className="field">
      <span className="field__label">{etiqueta}</span>
      <div>{valor || <span className="muted">—</span>}</div>
    </div>
  )
}
