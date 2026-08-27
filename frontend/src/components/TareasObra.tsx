/** Gestor de tareas de la obra: lista y tablero.
 *
 *  Dos vistas de lo mismo. La lista sirve para repasar y editar en frío; el
 *  tablero, para mover trabajo. El arrastre es HTML5 nativo, el mismo
 *  mecanismo que ya usa `RejillaEditable` — no hace falta una dependencia
 *  nueva para tres columnas.
 *
 *  Al soltar una tarjeta se manda columna y posición en una sola llamada, y el
 *  servidor renumera las dos columnas implicadas. Mandar solo el estado dejaría
 *  empates de `orden`, y con empates el tablero pinta las tarjetas en un orden
 *  que cambia entre recargas: de lo más difícil de diagnosticar después.
 */

import { useCallback, useEffect, useState } from 'react'
import {
  CalendarClock,
  Check,
  KanbanSquare,
  List,
  Plus,
  Trash2,
  User,
  X,
} from 'lucide-react'

import {
  COLUMNAS_TAREA,
  ETIQUETA_ESTADO_TAREA,
  ETIQUETA_PRIORIDAD,
  api,
} from '../lib/api'
import type { EstadoTarea, Personal, PrioridadTarea, Tarea } from '../lib/api'
import { EmptyState, ErrorNotice, Field, Modal, Tooltip } from './ui'

/** ¿Se le ha pasado la fecha? Una hecha tarde ya no pide nada. */
function vencida(tarea: Tarea): boolean {
  if (tarea.estado === 'hecha' || !tarea.fecha_limite) return false
  return tarea.fecha_limite < new Date().toISOString().slice(0, 10)
}

export function TareasObra({
  obraId,
  onCambio,
}: {
  obraId: string
  /** El cuadro de mandos tiene un contador de pendientes que hay que refrescar. */
  onCambio?: () => void
}) {
  const [tareas, setTareas] = useState<Tarea[] | null>(null)
  const [personal, setPersonal] = useState<Personal[]>([])
  const [vista, setVista] = useState<'tablero' | 'lista'>('tablero')
  const [error, setError] = useState<string | null>(null)
  const [creandoEn, setCreandoEn] = useState<EstadoTarea | null>(null)
  const [editando, setEditando] = useState<Tarea | null>(null)
  // Qué se arrastra y sobre qué hueco está: el índice es la posición donde
  // caería, no la tarjeta de debajo.
  const [arrastrada, setArrastrada] = useState<Tarea | null>(null)
  const [hueco, setHueco] = useState<{ estado: EstadoTarea; indice: number } | null>(null)

  const cargar = useCallback(async () => {
    try {
      setTareas(await api.obras.tareas(obraId))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [obraId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  useEffect(() => {
    api.personal
      .list({ activo: true, limit: 200 })
      .then((pagina) => setPersonal(pagina.items))
      .catch(() => setPersonal([]))
  }, [])

  async function soltar(estado: EstadoTarea, indice: number) {
    const tarea = arrastrada
    setArrastrada(null)
    setHueco(null)
    if (!tarea) return
    // Soltarla donde ya estaba no es un movimiento.
    if (tarea.estado === estado && tarea.orden === indice) return
    try {
      await api.tareas.mover(tarea.id, { estado, posicion: indice })
      await cargar()
      onCambio?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar(tarea: Tarea) {
    if (!window.confirm(`¿Eliminar la tarea «${tarea.titulo}»?`)) return
    try {
      await api.tareas.remove(tarea.id)
      await cargar()
      onCambio?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function cambiarEstado(tarea: Tarea, estado: EstadoTarea) {
    try {
      await api.tareas.update(tarea.id, { estado })
      await cargar()
      onCambio?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  if (tareas === null) return <p className="muted">Cargando…</p>

  const porColumna = (estado: EstadoTarea) =>
    tareas.filter((t) => t.estado === estado).sort((a, b) => a.orden - b.orden)

  return (
    <div className="form-section">
      <div className="page-head">
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Tareas</h2>
        <span className="page-head__acciones">
          <Tooltip texto={vista === 'tablero' ? 'Ver como lista' : 'Ver como tablero'}>
            <button
              className="btn"
              onClick={() => setVista(vista === 'tablero' ? 'lista' : 'tablero')}
            >
              {vista === 'tablero' ? <List size={16} /> : <KanbanSquare size={16} />}
              {vista === 'tablero' ? 'Lista' : 'Tablero'}
            </button>
          </Tooltip>
          <button className="btn btn--primary" onClick={() => setCreandoEn('pendiente')}>
            <Plus size={16} aria-hidden="true" />
            Nueva tarea
          </button>
        </span>
      </div>

      <ErrorNotice error={error} />

      {tareas.length === 0 ? (
        <EmptyState title="Sin tareas">
          Apunta lo que hay que hacer en la obra: se puede asignar a alguien de la plantilla y
          ponerle fecha.
        </EmptyState>
      ) : vista === 'tablero' ? (
        <div className="tablero">
          {COLUMNAS_TAREA.map((estado) => {
            const columna = porColumna(estado)
            return (
              <section
                key={estado}
                className={`tablero__columna${
                  hueco?.estado === estado ? ' tablero__columna--destino' : ''
                }`}
                onDragOver={(e) => {
                  if (!arrastrada) return
                  e.preventDefault()
                  // Sin tarjeta debajo, el hueco es el final de la columna.
                  setHueco((actual) =>
                    actual?.estado === estado ? actual : { estado, indice: columna.length },
                  )
                }}
                onDragLeave={(e) => {
                  // Solo cuando el puntero sale de la columna entera, no al
                  // pasar de una tarjeta a la siguiente.
                  if (!e.currentTarget.contains(e.relatedTarget as Node)) {
                    setHueco((actual) => (actual?.estado === estado ? null : actual))
                  }
                }}
                onDrop={(e) => {
                  e.preventDefault()
                  void soltar(estado, hueco?.estado === estado ? hueco.indice : columna.length)
                }}
              >
                <header className="tablero__cabecera">
                  <span>{ETIQUETA_ESTADO_TAREA[estado]}</span>
                  <span className="tablero__cuenta">{columna.length}</span>
                </header>

                <div className="tablero__pila">
                  {columna.map((tarea, indice) => (
                    <div key={tarea.id}>
                      {hueco?.estado === estado && hueco.indice === indice && (
                        <div className="tablero__hueco" aria-hidden="true" />
                      )}
                      <article
                        className={`tarjeta-tarea${
                          arrastrada?.id === tarea.id ? ' tarjeta-tarea--arrastrando' : ''
                        }${vencida(tarea) ? ' tarjeta-tarea--vencida' : ''}`}
                        draggable
                        onDragStart={() => setArrastrada(tarea)}
                        onDragEnd={() => {
                          setArrastrada(null)
                          setHueco(null)
                        }}
                        onDragOver={(e) => {
                          if (!arrastrada) return
                          e.preventDefault()
                          e.stopPropagation()
                          // Mitad de arriba: cae antes; mitad de abajo: después.
                          const caja = e.currentTarget.getBoundingClientRect()
                          const antes = e.clientY - caja.top < caja.height / 2
                          setHueco({ estado, indice: antes ? indice : indice + 1 })
                        }}
                        onClick={() => setEditando(tarea)}
                      >
                        <TarjetaContenido tarea={tarea} />
                      </article>
                    </div>
                  ))}
                  {hueco?.estado === estado && hueco.indice >= columna.length && (
                    <div className="tablero__hueco" aria-hidden="true" />
                  )}
                </div>

                <button
                  className="tablero__anadir"
                  onClick={() => setCreandoEn(estado)}
                >
                  <Plus size={14} aria-hidden="true" />
                  Añadir
                </button>
              </section>
            )
          })}
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Tarea</th>
                <th>Responsable</th>
                <th>Fecha límite</th>
                <th>Prioridad</th>
                <th>Estado</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {tareas.map((tarea) => (
                <tr key={tarea.id} className={vencida(tarea) ? 'fila-vencida' : undefined}>
                  <td>
                    <button className="enlace-plano" onClick={() => setEditando(tarea)}>
                      {tarea.titulo}
                    </button>
                    {tarea.descripcion && (
                      <div className="muted tarjeta-tarea__nota">{tarea.descripcion}</div>
                    )}
                  </td>
                  <td>{tarea.responsable_nombre ?? <span className="muted">—</span>}</td>
                  <td>
                    {tarea.fecha_limite ? (
                      vencida(tarea) ? (
                        <Tooltip texto="Fecha pasada y sin terminar">
                          <span className="cuadre--ojo">{tarea.fecha_limite}</span>
                        </Tooltip>
                      ) : (
                        tarea.fecha_limite
                      )
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <span className={`chip chip--prioridad-${tarea.prioridad}`}>
                      {ETIQUETA_PRIORIDAD[tarea.prioridad]}
                    </span>
                  </td>
                  <td>
                    <select
                      className="select select--sm"
                      value={tarea.estado}
                      onChange={(e) =>
                        void cambiarEstado(tarea, e.target.value as EstadoTarea)
                      }
                    >
                      {COLUMNAS_TAREA.map((estado) => (
                        <option key={estado} value={estado}>
                          {ETIQUETA_ESTADO_TAREA[estado]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="table__actions">
                    <Tooltip texto="Eliminar">
                      <button className="btn btn--sm" onClick={() => void eliminar(tarea)}>
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </Tooltip>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creandoEn && (
        <TareaModal
          obraId={obraId}
          estadoInicial={creandoEn}
          personal={personal}
          onClose={() => setCreandoEn(null)}
          onGuardada={() => {
            setCreandoEn(null)
            void cargar()
            onCambio?.()
          }}
        />
      )}

      {editando && (
        <TareaModal
          obraId={obraId}
          tarea={editando}
          personal={personal}
          onClose={() => setEditando(null)}
          onGuardada={() => {
            setEditando(null)
            void cargar()
            onCambio?.()
          }}
        />
      )}
    </div>
  )
}

function TarjetaContenido({ tarea }: { tarea: Tarea }) {
  return (
    <>
      <div className="tarjeta-tarea__cabecera">
        <span className={`tarjeta-tarea__prioridad tarjeta-tarea__prioridad--${tarea.prioridad}`}>
          {ETIQUETA_PRIORIDAD[tarea.prioridad]}
        </span>
        {tarea.estado === 'hecha' && tarea.completada_en && (
          <span className="muted tarjeta-tarea__nota">
            <Check size={11} aria-hidden="true" /> {tarea.completada_en}
          </span>
        )}
      </div>
      <strong className="tarjeta-tarea__titulo">{tarea.titulo}</strong>
      {tarea.descripcion && (
        <span className="tarjeta-tarea__nota">{tarea.descripcion}</span>
      )}
      <div className="tarjeta-tarea__pie">
        {tarea.responsable_nombre && (
          <span className="tarjeta-tarea__dato">
            <User size={11} aria-hidden="true" />
            {tarea.responsable_nombre}
          </span>
        )}
        {tarea.fecha_limite && (
          <span className="tarjeta-tarea__dato">
            <CalendarClock size={11} aria-hidden="true" />
            {tarea.fecha_limite}
          </span>
        )}
      </div>
    </>
  )
}

function TareaModal({
  obraId,
  tarea,
  estadoInicial,
  personal,
  onClose,
  onGuardada,
}: {
  obraId: string
  tarea?: Tarea
  estadoInicial?: EstadoTarea
  personal: Personal[]
  onClose: () => void
  onGuardada: () => void
}) {
  const [titulo, setTitulo] = useState(tarea?.titulo ?? '')
  const [descripcion, setDescripcion] = useState(tarea?.descripcion ?? '')
  const [responsable, setResponsable] = useState(tarea?.responsable_id ?? '')
  const [fecha, setFecha] = useState(tarea?.fecha_limite ?? '')
  const [estado, setEstado] = useState<EstadoTarea>(
    tarea?.estado ?? estadoInicial ?? 'pendiente',
  )
  const [prioridad, setPrioridad] = useState<PrioridadTarea>(tarea?.prioridad ?? 'normal')
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  async function guardar() {
    setGuardando(true)
    setError(null)
    const datos = {
      titulo: titulo.trim(),
      descripcion: descripcion.trim() || null,
      responsable_id: responsable || null,
      fecha_limite: fecha || null,
      estado,
      prioridad,
    }
    try {
      if (tarea) await api.tareas.update(tarea.id, datos)
      else await api.obras.addTarea(obraId, datos)
      onGuardada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setGuardando(false)
    }
  }

  return (
    <Modal title={tarea ? 'Editar tarea' : 'Nueva tarea'} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Qué hay que hacer">
          <input
            className="input"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            autoFocus
          />
        </Field>
        <Field label="Detalle">
          <textarea
            className="input"
            rows={3}
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
          />
        </Field>
        <div className="form-grid">
          <Field label="Responsable" hint="Alguien de la plantilla propia">
            <select
              className="select"
              value={responsable}
              onChange={(e) => setResponsable(e.target.value)}
            >
              <option value="">Sin asignar</option>
              {personal.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre} {p.apellidos ?? ''}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Fecha límite">
            <input
              className="input"
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </Field>
          <Field label="Prioridad">
            <select
              className="select"
              value={prioridad}
              onChange={(e) => setPrioridad(e.target.value as PrioridadTarea)}
            >
              {(Object.keys(ETIQUETA_PRIORIDAD) as PrioridadTarea[]).map((p) => (
                <option key={p} value={p}>
                  {ETIQUETA_PRIORIDAD[p]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Estado">
            <select
              className="select"
              value={estado}
              onChange={(e) => setEstado(e.target.value as EstadoTarea)}
            >
              {COLUMNAS_TAREA.map((e) => (
                <option key={e} value={e}>
                  {ETIQUETA_ESTADO_TAREA[e]}
                </option>
              ))}
            </select>
          </Field>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={titulo.trim() === '' || guardando}
          onClick={() => void guardar()}
        >
          {!guardando && <Check size={16} aria-hidden="true" />}
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </Modal>
  )
}
