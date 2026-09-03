import { useCallback, useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Plus } from 'lucide-react'

import { SubirPlanoModal } from '../components/SubirPlanoModal'
import { EmptyState, ErrorNotice } from '../components/ui'
import { api } from '../lib/api'
import type { Plano } from '../lib/api'
import { useToast } from '../toast'

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
        <SubirPlanoModal
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
