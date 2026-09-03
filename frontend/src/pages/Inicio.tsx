import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Star } from 'lucide-react'

import type { Widget } from '../components/WidgetGrid'
import { WidgetGrid } from '../components/WidgetGrid'
import { EmptyState, ErrorNotice, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import { ETIQUETA_ESTADO, ETIQUETA_ESTADO_OBRA } from '../lib/api'
import type { Favorito, Notificacion, ObraResumen, PresupuestoResumen } from '../lib/api'
import { useWorkspace } from '../workspace'

/** Página de inicio (Fase 1l): un dashboard básico de bloques que se pueden
 *  quitar, volver a traer, reordenar y redimensionar — el mismo `WidgetGrid`
 *  que ya usa la ficha de un presupuesto, aquí como pantalla de aterrizaje en
 *  vez de «Ajustes». Cada bloque es de solo lectura y enlaza a la pantalla
 *  de verdad; nada se edita desde aquí. */
export function Inicio() {
  const { principal, modules } = useWorkspace()
  const activo = (codigo: string) => modules.some((m) => m.code === codigo && m.is_active)

  const widgets: Widget[] = [
    {
      id: 'accesos',
      titulo: 'Accesos directos',
      x: 0,
      y: 0,
      w: 4,
      h: 9,
      minW: 3,
      minH: 4,
      contenido: <AccesosDirectos />,
    },
  ]
  if (activo('presupuestos')) {
    widgets.push({
      id: 'presupuestos',
      titulo: 'Presupuestos recientes',
      x: 4,
      y: 0,
      w: 8,
      h: 9,
      minW: 4,
      minH: 4,
      contenido: <PresupuestosRecientes />,
    })
  }
  if (activo('obras')) {
    widgets.push({
      id: 'obras',
      titulo: 'Obras en curso',
      x: 0,
      y: 9,
      w: 6,
      h: 9,
      minW: 4,
      minH: 4,
      contenido: <ObrasEnCurso />,
    })
  }
  widgets.push({
    id: 'notificaciones',
    titulo: 'Notificaciones',
    x: 6,
    y: 9,
    w: 6,
    h: 9,
    minW: 4,
    minH: 4,
    contenido: <NotificacionesRecientes />,
  })

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Hola, {principal?.username ?? ''}</h1>
          <p className="page-lead">
            Tu resumen de la cuenta. Reordena, redimensiona o quita cualquier bloque con el
            icono ⠿ de su cabecera — se recuerda en este navegador, y siempre puedes volver a
            traer uno oculto desde arriba.
          </p>
        </div>
      </div>
      <WidgetGrid id="inicio" widgets={widgets} />
    </div>
  )
}

function ListaCargando() {
  return <p className="muted">Cargando…</p>
}

function AccesosDirectos() {
  const [favoritos, setFavoritos] = useState<Favorito[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.yo.favoritos
      .list()
      .then(setFavoritos)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  if (error) return <ErrorNotice error={error} />
  if (favoritos === null) return <ListaCargando />
  if (favoritos.length === 0) {
    return (
      <EmptyState title="Sin accesos directos">
        Desde el menú de tu usuario (arriba a la derecha), «Guardar esta página» la deja aquí.
      </EmptyState>
    )
  }
  return (
    <ul className="lista">
      {favoritos.map((f) => (
        <li key={f.id}>
          <Link className="btn-enlace" to={f.ruta}>
            <Star size={13} aria-hidden="true" /> {f.etiqueta}
          </Link>
        </li>
      ))}
    </ul>
  )
}

function PresupuestosRecientes() {
  const [pagina, setPagina] = useState<PresupuestoResumen[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.presupuestos
      .list({ solo_ultima_version: true, limit: 8 })
      .then((p) => setPagina(p.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  if (error) return <ErrorNotice error={error} />
  if (pagina === null) return <ListaCargando />
  if (pagina.length === 0) {
    return (
      <EmptyState title="Sin presupuestos todavía">En cuanto crees uno, aparecerá aquí.</EmptyState>
    )
  }
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Código</th>
            <th>Obra</th>
            <th>Estado</th>
            <th className="table__num">Total</th>
          </tr>
        </thead>
        <tbody>
          {pagina.map((p) => (
            <tr key={p.id}>
              <td>
                <Link className="btn-enlace" to={`/presupuestos/${p.id}`}>
                  {p.codigo}
                </Link>
              </td>
              <td>{p.nombre}</td>
              <td>
                <span className={`chip chip--estado-${p.estado}`}>{ETIQUETA_ESTADO[p.estado]}</span>
              </td>
              <td className="table__num">{formatoImporte(p.total)} €</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ObrasEnCurso() {
  const [pagina, setPagina] = useState<ObraResumen[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.obras
      .list({ estado: 'en_ejecucion', limit: 8 })
      .then((p) => setPagina(p.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  if (error) return <ErrorNotice error={error} />
  if (pagina === null) return <ListaCargando />
  if (pagina.length === 0) {
    return (
      <EmptyState title="Sin obras en ejecución">Las obras en curso aparecerán aquí.</EmptyState>
    )
  }
  return (
    <ul className="lista">
      {pagina.map((o) => (
        <li key={o.id}>
          <Link className="btn-enlace" to={`/obras/${o.id}`}>
            {o.codigo} · {o.nombre}
          </Link>
          <span className="muted"> — {ETIQUETA_ESTADO_OBRA[o.estado]}</span>
        </li>
      ))}
    </ul>
  )
}

function NotificacionesRecientes() {
  const [lista, setLista] = useState<Notificacion[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.notificaciones
      .list(true)
      .then(setLista)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  if (error) return <ErrorNotice error={error} />
  if (lista === null) return <ListaCargando />
  if (lista.length === 0) {
    return <EmptyState title="Sin notificaciones pendientes">Al día.</EmptyState>
  }
  return (
    <ul className="lista">
      {lista.slice(0, 10).map((n) => (
        <li key={n.id}>
          {n.enlace ? (
            <Link className="btn-enlace" to={n.enlace}>
              {n.titulo}
            </Link>
          ) : (
            <span>{n.titulo}</span>
          )}
          {n.importante && <span className="badge badge--danger"> Importante</span>}
        </li>
      ))}
    </ul>
  )
}
