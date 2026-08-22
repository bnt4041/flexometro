import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowRight,
  BarChart3,
  Check,
  ClipboardCheck,
  Plus,
  Save,
  Trash2,
  UserPlus,
  X,
} from 'lucide-react'

import { CamposLibres } from '../components/CamposLibres'
import { ContactosAsociados } from '../components/ContactosAsociados'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { ETIQUETA_ESTADO_CERTIFICACION, ETIQUETA_ESTADO_OBRA, api } from '../lib/api'
import type {
  AsignacionDetalle,
  Certificacion,
  EstadoObra,
  ObraDetalle as Detalle,
  Personal,
} from '../lib/api'
import { useContextoObras } from './Obras'

/** Partida "plana" para elegir al certificar: el árbol de capítulos no
 *  importa aquí, solo qué partidas tiene la obra y cuánto llevan medido. */
interface PartidaPlana {
  id: string
  codigo: string
  resumen: string
  unidad: string
  medicion: string
}

function aplanarPartidas(nodos: { partidas: PartidaPlana[]; hijos: unknown[] }[]): PartidaPlana[] {
  const resultado: PartidaPlana[] = []
  const recorrer = (lista: typeof nodos) => {
    for (const nodo of lista) {
      resultado.push(...nodo.partidas)
      recorrer(nodo.hijos as typeof nodos)
    }
  }
  recorrer(nodos)
  return resultado
}

export function ObraDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoObras()
  const [obra, setObra] = useState<Detalle | null>(null)
  const [asignaciones, setAsignaciones] = useState<AsignacionDetalle[]>([])
  const [certificaciones, setCertificaciones] = useState<Certificacion[]>([])
  const [borrador, setBorrador] = useState<Partial<Detalle>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  const [asignando, setAsignando] = useState(false)
  const [midiendoPartes, setMidiendoPartes] = useState<AsignacionDetalle | null>(null)
  const [certificando, setCertificando] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const [detalle, lista, certs] = await Promise.all([
        api.obras.get(id),
        api.obras.asignaciones(id),
        api.certificaciones.list({ obra_id: id, limit: 100 }),
      ])
      setCertificaciones(certs.items)
      setObra(detalle)
      setAsignaciones(lista)
      setBorrador({})
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/obras')
  }

  if (error && !obra) {
    return (
      <ModalPantalla title="Obra" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!obra) return null

  const valor = <K extends keyof Detalle>(campo: K): Detalle[K] =>
    (borrador[campo] ?? obra[campo]) as Detalle[K]
  const cambiar = <K extends keyof Detalle>(campo: K, v: Detalle[K]) =>
    setBorrador((b) => ({ ...b, [campo]: v }))
  const hayCambios = Object.keys(borrador).length > 0

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      await api.obras.update(id, borrador)
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar «${obra!.nombre}»?`)) return
    try {
      await api.obras.remove(id)
      onCambio()
      cerrar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const pestanaDatos = (
    <>
      <ErrorNotice error={error} />

      <div className="card">
        <div className="form-section">
          <div className="form-section__title">Datos de la obra</div>
          <div className="form-grid">
            <Field ancho="doble" label="Nombre">
              <input
                className="input"
                value={valor('nombre')}
                onChange={(e) => cambiar('nombre', e.target.value)}
              />
            </Field>
            <Field label="Estado">
              <select
                className="select"
                value={valor('estado')}
                onChange={(e) => cambiar('estado', e.target.value as EstadoObra)}
              >
                {Object.entries(ETIQUETA_ESTADO_OBRA).map(([clave, etiqueta]) => (
                  <option key={clave} value={clave}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Fecha de inicio">
              <input
                className="input"
                type="date"
                value={valor('fecha_inicio') ?? ''}
                onChange={(e) => cambiar('fecha_inicio', e.target.value || null)}
              />
            </Field>
            <Field label="Fin previsto">
              <input
                className="input"
                type="date"
                value={valor('fecha_fin_prevista') ?? ''}
                onChange={(e) => cambiar('fecha_fin_prevista', e.target.value || null)}
              />
            </Field>
            <Field label="Fin real">
              <input
                className="input"
                type="date"
                value={valor('fecha_fin_real') ?? ''}
                onChange={(e) => cambiar('fecha_fin_real', e.target.value || null)}
              />
            </Field>
          </div>
        </div>

        <div className="form-actions">
          <button className="btn" disabled={!hayCambios} onClick={() => setBorrador({})}>
            <X size={16} aria-hidden="true" />
            Descartar
          </button>
          <button
            className="btn btn--primary"
            disabled={!hayCambios || guardando}
            onClick={() => void guardar()}
          >
            {!guardando && <Save size={16} aria-hidden="true" />}
            {guardando ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>

      <CamposLibres entidad="obra" entidadId={id} />

      <div className="page-head" style={{ marginTop: 'var(--sp-6)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Personal asignado</h2>
        <Tooltip texto="Asignar un trabajador a esta obra">
          <button className="btn" onClick={() => setAsignando(true)}>
            <UserPlus size={16} aria-hidden="true" />
            Asignar trabajador
          </button>
        </Tooltip>
      </div>

      <div className="table-wrap">
        {asignaciones.length === 0 ? (
          <EmptyState title="Sin personal asignado">
            Asigna trabajadores para empezar a registrar horas y coste real de mano de obra.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Trabajador</th>
                <th>Desde</th>
                <th>Hasta</th>
                <th className="table__num">Coste/hora</th>
                <th className="table__num">Horas</th>
                <th className="table__num">Coste</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {asignaciones.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.personal_nombre}{' '}
                    {a.personal_categoria && <span className="muted">({a.personal_categoria})</span>}
                  </td>
                  <td>{a.fecha_desde}</td>
                  <td>{a.fecha_hasta ?? <span className="muted">—</span>}</td>
                  <td className="table__num">{formatoImporte(a.coste_hora)}</td>
                  <td className="table__num">{formatoImporte(a.horas_totales, 1)}</td>
                  <td className="table__num">
                    <strong>{formatoImporte(a.coste_total)}</strong>
                  </td>
                  <td className="table__actions">
                    <button className="btn btn--sm" onClick={() => setMidiendoPartes(a)}>
                      <ClipboardCheck size={14} aria-hidden="true" />
                      Partes de trabajo
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="page-head" style={{ marginTop: 'var(--sp-6)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Certificaciones</h2>
        <Tooltip texto="Certificar lo ejecutado hasta la fecha">
          <button className="btn" onClick={() => setCertificando(true)}>
            <Plus size={16} aria-hidden="true" />
            Nueva certificación
          </button>
        </Tooltip>
      </div>

      <div className="table-wrap">
        {certificaciones.length === 0 ? (
          <EmptyState title="Sin certificaciones">
            Certifica lo ejecutado hasta la fecha para poder facturarlo.
          </EmptyState>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Nº</th>
                <th>Fecha</th>
                <th>Estado</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {certificaciones.map((c) => (
                <tr key={c.id}>
                  <td className="table__code">{c.codigo}</td>
                  <td>{c.fecha}</td>
                  <td>
                    <span className={`chip chip--estado-cert-${c.estado}`}>
                      {ETIQUETA_ESTADO_CERTIFICACION[c.estado]}
                    </span>
                  </td>
                  <td className="table__actions">
                    <Link className="btn btn--sm" to={`/certificaciones/${c.id}`}>
                      Ver certificación nº {c.numero}
                      <ArrowRight size={14} aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {certificando && (
        <NuevaCertificacionModal
          obraId={id}
          presupuestoId={obra.presupuesto_id}
          onClose={() => setCertificando(false)}
          onCreada={(certId) => navigate(`/certificaciones/${certId}`)}
        />
      )}

      {asignando && (
        <AsignarModal
          obraId={id}
          onClose={() => setAsignando(false)}
          onAsignado={() => {
            setAsignando(false)
            void cargar()
          }}
        />
      )}

      {midiendoPartes && (
        <PartesModal
          asignacion={midiendoPartes}
          onClose={() => setMidiendoPartes(null)}
          onCambio={cargar}
        />
      )}
    </>
  )

  const pestanas: PestanaFicha[] = [
    { id: 'datos', etiqueta: 'Datos', icono: 'datos', contenido: pestanaDatos },
    {
      id: 'contactos',
      etiqueta: 'Contactos',
      icono: 'contactos',
      contenido: <ContactosAsociados entidad="obra" entidadId={id} />,
    },
    {
      id: 'crm',
      etiqueta: 'CRM',
      icono: 'crm',
      contenido: <NotasCrm entidad="obra" entidadId={id} />,
    },
    {
      id: 'documentos',
      etiqueta: 'Documentos',
      icono: 'documentos',
      contenido: <Documentos entidad="obra" entidadId={id} />,
    },
    {
      id: 'historial',
      etiqueta: 'Historial',
      icono: 'historial',
      contenido: <Historial cargar={() => api.obras.historial(id)} />,
    },
  ]

  return (
    <FichaDetalle
      titulo={
        <>
          {obra.nombre} <span className="table__code">{obra.codigo}</span>
        </>
      }
      subtitulo={
        <p className="page-lead" style={{ marginBottom: 0 }}>
          Presupuesto{' '}
          <Link to={`/presupuestos/${obra.presupuesto_id}`}>{obra.presupuesto_codigo}</Link>
        </p>
      }
      acciones={
        <>
          <Tooltip texto="Comparar coste real frente a lo presupuestado">
            <button className="btn btn--primary" onClick={() => navigate(`/obras/${id}/costes`)}>
              <BarChart3 size={16} aria-hidden="true" />
              Coste real vs. presupuestado
            </button>
          </Tooltip>
          <Tooltip texto="Eliminar esta obra">
            <button className="btn btn--danger" onClick={() => void eliminar()}>
              <Trash2 size={16} aria-hidden="true" />
              Eliminar
            </button>
          </Tooltip>
        </>
      }
      pestanas={pestanas}
      onClose={cerrar}
    />
  )
}

function AsignarModal({
  obraId,
  onClose,
  onAsignado,
}: {
  obraId: string
  onClose: () => void
  onAsignado: () => void
}) {
  const [personal, setPersonal] = useState<Personal[]>([])
  const [personalId, setPersonalId] = useState('')
  const [fechaDesde, setFechaDesde] = useState(new Date().toISOString().slice(0, 10))
  const [costeHora, setCosteHora] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void api.personal
      .list({ activo: true, limit: 500 })
      .then((page) => {
        setPersonal(page.items)
        if (page.items.length > 0) {
          setPersonalId(page.items[0].id)
          setCosteHora(page.items[0].coste_hora)
        }
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [])

  function elegir(pid: string) {
    setPersonalId(pid)
    const p = personal.find((x) => x.id === pid)
    if (p) setCosteHora(p.coste_hora)
  }

  async function guardar() {
    setError(null)
    try {
      await api.obras.addAsignacion(obraId, {
        personal_id: personalId,
        fecha_desde: fechaDesde,
        coste_hora: costeHora || null,
      })
      onAsignado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Asignar trabajador a la obra" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        {personal.length === 0 ? (
          <EmptyState title="No hay personal de alta">
            Da de alta trabajadores en la pantalla Personal antes de asignarlos.
          </EmptyState>
        ) : (
          <div className="form-grid">
            <Field label="Trabajador">
              <select className="select" value={personalId} onChange={(e) => elegir(e.target.value)}>
                {personal.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nombre} {p.apellidos ?? ''} {p.categoria ? `— ${p.categoria}` : ''}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Desde">
              <input
                className="input"
                type="date"
                value={fechaDesde}
                onChange={(e) => setFechaDesde(e.target.value)}
              />
            </Field>
            <Field label="Coste/hora en esta obra" hint="Se congela: cambiar la ficha luego no lo altera">
              <input
                className="input"
                type="number"
                step="0.01"
                value={costeHora}
                onChange={(e) => setCosteHora(e.target.value)}
              />
            </Field>
          </div>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={personal.length === 0}
          onClick={() => void guardar()}
        >
          <Plus size={16} aria-hidden="true" />
          Asignar
        </button>
      </div>
    </Modal>
  )
}

function PartesModal({
  asignacion,
  onClose,
  onCambio,
}: {
  asignacion: AsignacionDetalle
  onClose: () => void
  onCambio: () => void
}) {
  const [detalle, setDetalle] = useState<AsignacionDetalle>(asignacion)
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [horas, setHoras] = useState('8')
  const [error, setError] = useState<string | null>(null)

  const recargar = useCallback(async () => {
    try {
      setDetalle(await api.asignaciones.get(asignacion.id))
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [asignacion.id, onCambio])

  async function anadir() {
    setError(null)
    try {
      await api.asignaciones.addParte(asignacion.id, { fecha, horas })
      await recargar()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function eliminar(parteId: string) {
    await api.partesTrabajo.remove(parteId)
    await recargar()
  }

  return (
    <Modal title={`Partes de trabajo · ${detalle.personal_nombre}`} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th className="table__num">Horas</th>
                <th className="table__num">Coste</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {detalle.partes.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <EmptyState title="Sin partes registrados" />
                  </td>
                </tr>
              ) : (
                detalle.partes.map((p) => (
                  <tr key={p.id}>
                    <td>{p.fecha}</td>
                    <td className="table__num">{formatoImporte(p.horas, 2)}</td>
                    <td className="table__num">{formatoImporte(p.coste)}</td>
                    <td className="table__actions">
                      <Tooltip texto="Eliminar este parte">
                        <button
                          className="btn btn--sm btn--danger btn--solo-icono"
                          onClick={() => void eliminar(p.id)}
                        >
                          <Trash2 size={14} aria-hidden="true" />
                        </button>
                      </Tooltip>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
            <tfoot>
              <tr className="fila-total">
                <td className="table__num total-label">Total</td>
                <td className="table__num">{formatoImporte(detalle.horas_totales, 1)}</td>
                <td className="table__num">
                  <strong>{formatoImporte(detalle.coste_total)}</strong>
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
          <Field label="Fecha">
            <input
              className="input"
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </Field>
          <Field label="Horas">
            <input
              className="input"
              type="number"
              step="0.5"
              value={horas}
              onChange={(e) => setHoras(e.target.value)}
            />
          </Field>
        </div>
        <div style={{ marginTop: 'var(--sp-3)' }}>
          <button className="btn" onClick={() => void anadir()}>
            <Plus size={16} aria-hidden="true" />
            Añadir parte
          </button>
        </div>
      </div>

      <CamposLibres entidad="asignacion" entidadId={asignacion.id} />

      <div className="form-actions">
        <button className="btn btn--primary" onClick={onClose}>
          <Check size={16} aria-hidden="true" />
          Hecho
        </button>
      </div>
    </Modal>
  )
}

function NuevaCertificacionModal({
  obraId,
  presupuestoId,
  onClose,
  onCreada,
}: {
  obraId: string
  presupuestoId: string
  onClose: () => void
  onCreada: (certificacionId: string) => void
}) {
  const [partidas, setPartidas] = useState<PartidaPlana[]>([])
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [retencion, setRetencion] = useState('0.00')
  const [medidas, setMedidas] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)

  useEffect(() => {
    void api.presupuestos
      .get(presupuestoId)
      .then((p) => setPartidas(aplanarPartidas(p.capitulos as never)))
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [presupuestoId])

  async function guardar() {
    setGuardando(true)
    setError(null)
    try {
      const lineas = Object.entries(medidas)
        .filter(([, valor]) => valor.trim() !== '')
        .map(([partida_id, medicion_actual]) => ({ partida_id, medicion_actual }))
      if (lineas.length === 0) {
        setError('Indica la medición acumulada de al menos una partida')
        setGuardando(false)
        return
      }
      const certificacion = await api.certificaciones.create({
        obra_id: obraId,
        fecha,
        retencion_garantia_pct: retencion,
        lineas,
      })
      onCreada(certificacion.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setGuardando(false)
    }
  }

  return (
    <Modal title="Nueva certificación" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          Indica cuánto lleva ejecutado en total cada partida, no lo de este periodo: el importe
          a certificar se calcula solo, restando lo ya certificado antes.
        </p>
        <div className="form-grid">
          <Field label="Fecha">
            <input
              className="input"
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          </Field>
          <Field label="Retención de garantía (%)" hint="0 si no aplica">
            <input
              className="input"
              type="number"
              step="0.01"
              value={retencion}
              onChange={(e) => setRetencion(e.target.value)}
            />
          </Field>
        </div>

        <div className="table-wrap" style={{ marginTop: 'var(--sp-4)' }}>
          {partidas.length === 0 ? (
            <EmptyState title="El presupuesto no tiene partidas" />
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Partida</th>
                  <th className="table__num">Presupuestado</th>
                  <th className="table__num" style={{ width: 140 }}>
                    Medición acumulada
                  </th>
                </tr>
              </thead>
              <tbody>
                {partidas.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <span className="table__code">{p.codigo}</span> {p.resumen}
                    </td>
                    <td className="table__num">
                      {formatoImporte(p.medicion, 3)} {p.unidad}
                    </td>
                    <td className="table__num">
                      <input
                        className="input input--celda"
                        type="number"
                        step="0.001"
                        value={medidas[p.id] ?? ''}
                        onChange={(e) =>
                          setMedidas((m) => ({ ...m, [p.id]: e.target.value }))
                        }
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          <X size={16} aria-hidden="true" />
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={guardando} onClick={() => void guardar()}>
          {!guardando && <Plus size={16} aria-hidden="true" />}
          {guardando ? 'Creando…' : 'Crear certificación'}
        </button>
      </div>
    </Modal>
  )
}
