import { useCallback, useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Plus, Upload } from 'lucide-react'

import { EmptyState, ErrorNotice, Field, Modal } from '../components/ui'
import { api } from '../lib/api'
import type { Plano } from '../lib/api'
import { esDxf, leerHojas } from '../lib/hojasPlano'
import { useToast } from '../toast'

const ADMITIDOS = '.pdf,.png,.jpg,.jpeg,.webp,.dxf'

/** La biblioteca. El plano en sí se abre en su propia ruta (`/planos/:id`),
 *  que monta el editor a pantalla completa. */
export function Planos() {
  const { notificar } = useToast()
  const navigate = useNavigate()
  const [planos, setPlanos] = useState<Plano[]>([])
  const [subiendo, setSubiendo] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      setPlanos(await api.planos.list())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    void cargar()
  }, [cargar])

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Planos</h1>
          <p className="page-lead">
            En DXF se mide pinchando la entidad y el número es exacto. En PDF o
            imagen hay que calibrar primero sobre una cota conocida. En los dos casos
            lo medido puede irse a una partida como una línea de medición más.
          </p>
        </div>
        <button type="button" className="btn btn--primary" onClick={() => setSubiendo(true)}>
          <Plus size={16} aria-hidden="true" /> Subir plano
        </button>
      </div>

      <ErrorNotice error={error} />

      {!cargando && planos.length === 0 ? (
        <EmptyState title="No hay planos todavía">
          Admite DXF, PDF e imágenes. Un DXF trae sus capas y casi siempre sus
          unidades, así que se puede medir nada más subirlo; un PDF o una foto hay
          que calibrarlos primero sobre una cota conocida.
        </EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Archivo</th>
                <th>Subido por</th>
              </tr>
            </thead>
            <tbody>
              {planos.map((p) => (
                <tr
                  key={p.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/planos/${p.id}`)}
                >
                  <td>{p.codigo}</td>
                  <td>{p.nombre}</td>
                  <td className="muted">{p.nombre_archivo}</td>
                  <td className="muted">{p.creado_por_nombre ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {subiendo && (
        <SubirPlano
          onCerrar={() => setSubiendo(false)}
          onSubido={(p) => {
            setSubiendo(false)
            notificar(`${p.codigo} subido`)
            navigate(`/planos/${p.id}`)
          }}
        />
      )}

      <Outlet />
    </div>
  )
}

function SubirPlano({
  onCerrar,
  onSubido,
}: {
  onCerrar: () => void
  onSubido: (p: Plano) => void
}) {
  const [archivo, setArchivo] = useState<File | null>(null)
  const [nombre, setNombre] = useState('')
  const [descripcion, setDescripcion] = useState('')
  const [hojas, setHojas] = useState<number | null>(null)
  const [vectorial, setVectorial] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ocupado, setOcupado] = useState(false)

  async function elegir(fichero: File) {
    setArchivo(fichero)
    setError(null)
    setVectorial(esDxf(fichero))
    // El nombre se propone del fichero, sin extensión: casi siempre es el
    // bueno, y teclearlo otra vez es trabajo tonto.
    if (!nombre) setNombre(fichero.name.replace(/\.[^.]+$/, ''))
    try {
      setHojas((await leerHojas(fichero)).length)
    } catch (err) {
      setHojas(null)
      setError(err instanceof Error ? err.message : 'No se ha podido leer el fichero')
    }
  }

  async function subir() {
    if (!archivo) return
    setOcupado(true)
    setError(null)
    try {
      const leidas = await leerHojas(archivo)
      onSubido(await api.planos.subir({ nombre, descripcion }, archivo, leidas))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setOcupado(false)
    }
  }

  return (
    <Modal title="Subir plano" onClose={onCerrar}>
      <ErrorNotice error={error} />
      <Field label="Archivo">
        <input
          type="file"
          className="input"
          accept={ADMITIDOS}
          onChange={(e) => e.target.files?.[0] && void elegir(e.target.files[0])}
        />
      </Field>
      {vectorial ? (
        <p className="muted">
          DXF. Se lee en el servidor: sus capas se crean solas y, si el fichero
          declara sus unidades, ya viene calibrado y se puede medir sin pinchar
          ninguna cota.
        </p>
      ) : (
        hojas !== null && (
          <p className="muted">
            {hojas === 1 ? '1 hoja' : `${hojas} hojas`}. Cada una se calibra por separado.
          </p>
        )
      )}
      <Field label="Nombre">
        <input className="input" value={nombre} onChange={(e) => setNombre(e.target.value)} />
      </Field>
      <Field label="Descripción">
        <textarea
          className="input"
          rows={3}
          value={descripcion}
          onChange={(e) => setDescripcion(e.target.value)}
        />
      </Field>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={ocupado || !archivo || !nombre.trim()}
          onClick={() => void subir()}
        >
          <Upload size={16} aria-hidden="true" /> Subir
        </button>
      </div>
    </Modal>
  )
}
