import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  BarChart3,
  Check,
  ClipboardCheck,
  Plus,
  Save,
  Sparkles,
  Trash2,
  Upload,
  UserPlus,
  X,
} from 'lucide-react'

import { CamposLibres } from '../components/CamposLibres'
import { Comparativo } from '../components/Comparativo'
import { CuadroObra } from '../components/CuadroObra'
import { TareasObra } from '../components/TareasObra'
import { ComprasObra } from '../components/ComprasObra'
import { VentasObra } from '../components/VentasObra'
import { DocumentoIAModal } from '../components/DocumentoIAModal'
import { MedicionesObra } from '../components/MedicionesObra'
import { RejillaObra } from '../components/RejillaObra'
import { WidgetGrid } from '../components/WidgetGrid'
import { ContactosAsociados } from '../components/ContactosAsociados'
import { Documentos } from '../components/Documentos'
import type { PestanaFicha } from '../components/FichaDetalle'
import { PresupuestosObra } from '../components/PresupuestosObra'
import { FichaDetalle } from '../components/FichaDetalle'
import { Historial } from '../components/Historial'
import { NotasCrm } from '../components/NotasCrm'
import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, Tooltip, formatoImporte } from '../components/ui'
import { ETIQUETA_ESTADO_OBRA, api } from '../lib/api'
import type {
  ArbolObra,
  AsignacionDetalle,
  Certificacion,
  EstadoObra,
  NodoObra,
  ObraDetalle as Detalle,
  PartidaObra,
  Personal,
  VinculoPresupuesto,
} from '../lib/api'
import { useContextoObras } from './Obras'
import { useWorkspace } from '../workspace'

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

/** Vuelve a encontrar una partida en el árbol recién cargado. Sin esto, la
 *  selección se quedaría congelada en la copia del momento del clic. */
function buscarPartida(nodos: NodoObra[], partidaId: string): PartidaObra | null {
  for (const nodo of nodos) {
    const encontrada = nodo.partidas.find((p) => p.id === partidaId)
    if (encontrada) return encontrada
    const enHijos = buscarPartida(nodo.hijos, partidaId)
    if (enHijos) return enHijos
  }
  return null
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
  const [arbol, setArbol] = useState<ArbolObra | null>(null)
  const [vinculos, setVinculos] = useState<VinculoPresupuesto[]>([])
  const [seleccion, setSeleccion] = useState<PartidaObra | null>(null)
  const [sincronizando, setSincronizando] = useState(false)
  // Un contador, no los datos: mover una tarea tiene que refrescar el widget
  // de pendientes del cuadro de mandos, y ese los pide por su cuenta.
  const [refrescoTareas, setRefrescoTareas] = useState(0)

  const cargar = useCallback(async () => {
    try {
      const [detalle, lista, certs, arbolObra, vinculosObra] = await Promise.all([
        api.obras.get(id),
        api.obras.asignaciones(id),
        api.certificaciones.list({ obra_id: id, limit: 100 }),
        api.obras.arbol(id),
        api.obras.presupuestos(id),
      ])
      setCertificaciones(certs.items)
      setObra(detalle)
      setAsignaciones(lista)
      setArbol(arbolObra)
      setVinculos(vinculosObra)
      // La partida seleccionada se relee del árbol recién cargado: guardar la
      // copia del momento del clic dejaría el widget de mediciones enseñando
      // la medición de antes de la última edición.
      setSeleccion((actual) => {
        if (actual === null) return null
        const fresca = buscarPartida(arbolObra.capitulos, actual.id)
        return fresca ?? null
      })
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

  async function sincronizarArbol() {
    setSincronizando(true)
    try {
      await api.obras.sincronizarArbol(id)
      await cargar()
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setSincronizando(false)
    }
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

        <div className="form-actions form-actions--separadas">
          <Tooltip texto="Eliminar esta obra">
            <button className="btn btn--danger" onClick={() => void eliminar()}>
              <Trash2 size={16} aria-hidden="true" />
              Eliminar
            </button>
          </Tooltip>
          <span className="form-actions__grupo">
            <Tooltip texto="Comparar coste real frente a lo presupuestado">
              <button className="btn" onClick={() => navigate(`/obras/${id}/costes`)}>
                <BarChart3 size={16} aria-hidden="true" />
                Coste real vs. presupuestado
              </button>
            </Tooltip>
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
          </span>
        </div>
      </div>

      <CamposLibres entidad="obra" entidadId={id} />

      <PresupuestosObra obraId={id} onCambio={() => void cargar()} />

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

  /** Pestaña «Partidas»: el árbol de la obra y su medición real, con la misma
   *  disposición de widgets que en presupuestos (arrastrables, ocultables, y
   *  la posición guardada en el navegador). */
  const pestanaPartidas = (
    <>
      <ErrorNotice error={error} />

      {arbol !== null && arbol.capitulos.length === 0 && (
        <div className="notice notice--aviso">
          <span>
            Esta obra todavía no tiene árbol propio. Puedes traer las partidas de sus
            presupuestos vinculados: se copian, y a partir de ahí lo que midas en obra no toca el
            presupuesto firmado con el cliente.
          </span>
          <button
            className="btn btn--sm"
            disabled={sincronizando}
            onClick={() => void sincronizarArbol()}
          >
            {sincronizando ? 'Trayendo…' : 'Traer partidas de los presupuestos'}
          </button>
        </div>
      )}

      {arbol !== null && (
        <WidgetGrid
          id="obra-partidas"
          widgets={[
            {
              id: 'arbol',
              titulo: 'Capítulos y partidas de la obra',
              x: 0,
              y: 0,
              w: 8,
              h: 12,
              minW: 4,
              minH: 6,
              contenido: (
                <RejillaObra
                  obraId={id}
                  arbol={arbol}
                  onCambio={cargar}
                  onMedir={setSeleccion}
                  seleccionadaId={seleccion?.id ?? null}
                  onSeleccionar={(fila) =>
                    setSeleccion(fila?.tipo === 'partida' && fila.partida ? fila.partida : null)
                  }
                />
              ),
            },
            {
              id: 'resumen',
              titulo: 'Resumen',
              x: 8,
              y: 0,
              w: 4,
              h: 12,
              minW: 3,
              minH: 6,
              contenido: <ResumenArbol arbol={arbol} vinculos={vinculos} />,
            },
            {
              id: 'mediciones',
              titulo: 'Medición de obra',
              x: 0,
              y: 12,
              w: 12,
              h: 11,
              minW: 5,
              minH: 5,
              contenido:
                seleccion === null ? (
                  <EmptyState title="Ninguna partida seleccionada">
                    Elige una partida del árbol para medir lo ejecutado.
                  </EmptyState>
                ) : (
                  <MedicionesObra partida={seleccion} onCambio={cargar} />
                ),
            },
          ]}
        />
      )}
    </>
  )

  const codigosPresupuesto = new Map(
    vinculos.map((v) => [v.presupuesto_id, v.presupuesto_codigo]),
  )

  const pestanas: PestanaFicha[] = [
    {
      id: 'cuadro',
      etiqueta: 'Cuadro de mandos',
      icono: 'calculator',
      contenido: (
        <CuadroObra
          obraId={id}
          arbol={arbol}
          certificaciones={certificaciones}
          refresco={refrescoTareas}
        />
      ),
    },
    { id: 'datos', etiqueta: 'Datos', icono: 'datos', contenido: pestanaDatos },
    { id: 'partidas', etiqueta: 'Partidas', icono: 'medir', contenido: pestanaPartidas },
    {
      id: 'comparativo',
      etiqueta: 'Comparativo',
      icono: 'comparativo',
      contenido: (
        <Comparativo
          obraId={id}
          codigosPresupuesto={codigosPresupuesto}
          onAprobado={() => void cargar()}
        />
      ),
    },
    {
      id: 'compras',
      etiqueta: 'Compras',
      icono: 'truck',
      contenido: <ComprasObra obraId={id} />,
    },
    {
      id: 'ventas',
      etiqueta: 'Ventas',
      icono: 'receipt',
      contenido: (
        <VentasObra
          obraId={id}
          certificaciones={certificaciones}
          onCertificar={() => setCertificando(true)}
        />
      ),
    },
    {
      id: 'tareas',
      etiqueta: 'Tareas',
      icono: 'confirmar',
      contenido: <TareasObra obraId={id} onCambio={() => setRefrescoTareas((n) => n + 1)} />,
    },
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
    <>
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
        pestanas={pestanas}
        onClose={cerrar}
      />

      {/* Fuera de las pestañas a propósito: FichaDetalle solo monta el
       *  contenido de la pestaña activa, y «crear certificación» se dispara
       *  desde Ventas — si el modal viviera dentro de una pestaña concreta,
       *  solo aparecería al entrar en esa pestaña. */}
      {certificando && (
        <NuevaCertificacionModal
          obraId={id}
          presupuestoId={obra.presupuesto_id}
          onClose={() => setCertificando(false)}
          onCreada={(certId) => navigate(`/certificaciones/${certId}`)}
        />
      )}
    </>
  )
}

/** Widget «Resumen»: lo contratado frente a lo que la obra dice hoy.
 *
 *  La cifra que importa es la desviación por los anexos: es lo que se ha
 *  contratado DESPUÉS de arrancar y lo que hay que poder justificar. */
function ResumenArbol({
  arbol,
  vinculos,
}: {
  arbol: ArbolObra
  vinculos: VinculoPresupuesto[]
}) {
  const t = arbol.totales
  const anexos = vinculos.filter((v) => v.tipo === 'anexo')
  const margen = Number(t.venta) - Number(t.coste)
  const margenPct = Number(t.venta) > 0 ? (margen / Number(t.venta)) * 100 : 0

  return (
    <div className="ficha-datos">
      <dl className="resumen-obra">
        <div>
          <dt>Coste de obra</dt>
          <dd>{formatoImporte(t.coste)} €</dd>
        </div>
        <div>
          <dt>Venta (a certificar)</dt>
          <dd>{formatoImporte(t.venta)} €</dd>
        </div>
        <div>
          <dt>Margen</dt>
          <dd>
            {formatoImporte(String(margen))} €{' '}
            <span className="muted">({margenPct.toFixed(1)} %)</span>
          </dd>
        </div>
        <div className="resumen-obra__separado">
          <dt>De ello, anexos</dt>
          <dd>
            {formatoImporte(t.coste_anexos)} € de coste
            <div className="muted">{formatoImporte(t.venta_anexos)} € de venta</div>
          </dd>
        </div>
        <div>
          <dt>Presupuestos en ejecución</dt>
          <dd>
            {vinculos.length}{' '}
            <span className="muted">
              {anexos.length === 0
                ? '(solo el principal)'
                : anexos.length === 1
                  ? '(1 anexo)'
                  : `(${anexos.length} anexos)`}
            </span>
          </dd>
        </div>
      </dl>
    </div>
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
  const { modules } = useWorkspace()
  const iaActiva = modules.some((m) => m.code === 'ia' && m.is_active)
  const [partidas, setPartidas] = useState<PartidaPlana[]>([])
  const [fecha, setFecha] = useState(new Date().toISOString().slice(0, 10))
  const [retencion, setRetencion] = useState('0.00')
  const [medidas, setMedidas] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [guardando, setGuardando] = useState(false)
  // Arrastrar un documento (un parte de obra, la certificación anterior...)
  // rellena `medidas` con lo que la IA proponga — nunca se guarda nada por
  // su cuenta, el usuario sigue revisando y creando la certificación por el
  // camino normal.
  const [documentoIA, setDocumentoIA] = useState<File[] | null>(null)
  const [arrastrando, setArrastrando] = useState(false)
  const inputFicheroRef = useRef<HTMLInputElement>(null)

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

  function resolverPartida(partidaId: string): string {
    const p = partidas.find((x) => x.id === partidaId)
    return p ? `${p.codigo} — ${p.resumen}` : partidaId
  }

  return (
    <>
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

        {iaActiva && partidas.length > 0 && (
          <div
            className="form-actions"
            style={{ marginTop: 'var(--sp-4)', marginBottom: 0 }}
          >
            <button className="btn btn--sm" onClick={() => setDocumentoIA([])}>
              <Sparkles size={14} aria-hidden="true" />
              Preguntar a la IA
            </button>
            <button className="btn btn--sm" onClick={() => inputFicheroRef.current?.click()}>
              <Upload size={14} aria-hidden="true" />
              Subir documento (PDF, imagen o Excel)…
            </button>
            <span className="muted">o arrastra uno sobre la tabla</span>
          </div>
        )}

        <div
          className={
            arrastrando ? 'table-wrap table-wrap--arrastrando' : 'table-wrap'
          }
          style={{ marginTop: 'var(--sp-4)' }}
          onDragOver={(e) => {
            if (!iaActiva || !e.dataTransfer.types.includes('Files')) return
            e.preventDefault()
            setArrastrando(true)
          }}
          onDragLeave={() => setArrastrando(false)}
          onDrop={(e) => {
            if (!iaActiva || !e.dataTransfer.types.includes('Files')) return
            e.preventDefault()
            setArrastrando(false)
            const archivos = Array.from(e.dataTransfer.files)
            if (archivos.length > 0) setDocumentoIA(archivos)
          }}
        >
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

    <input
      ref={inputFicheroRef}
      type="file"
      multiple
      accept=".xlsx,application/pdf,image/png,image/jpeg,image/webp"
      style={{ display: 'none' }}
      onChange={(e) => {
        const archivos = Array.from(e.target.files ?? [])
        e.target.value = ''
        if (archivos.length > 0) setDocumentoIA(archivos)
      }}
    />

    {documentoIA && (
      <DocumentoIAModal
        ficheros={documentoIA}
        entidad="obra"
        entidadId={obraId}
        conversar={(ficheros, mensajes) =>
          api.certificaciones.documentoConversarIA(obraId, presupuestoId, ficheros, mensajes)
        }
        resolverPartida={resolverPartida}
        aplicarPropuesta={async (propuesta) => {
          const lineas = propuesta.lineas_certificacion_propuestas ?? []
          setMedidas((m) => {
            const copia = { ...m }
            for (const l of lineas) copia[l.partida_id] = l.medicion_actual
            return copia
          })
          return `Hecho: medición rellenada en ${lineas.length} partida${lineas.length === 1 ? '' : 's'} — revísala antes de crear la certificación.`
        }}
        onClose={() => setDocumentoIA(null)}
      />
    )}
    </>
  )
}
