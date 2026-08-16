import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { CamposLibres } from '../components/CamposLibres'
import { EmptyState, ErrorNotice, Field, Modal, ModalPantalla, formatoImporte } from '../components/ui'
import { ETIQUETA_ESTADO, api, descargar } from '../lib/api'
import type {
  Concepto,
  EstadoPresupuesto,
  LecturaPlanoDetalle,
  LineaSugerida,
  NodoCapitulo,
  Partida,
  PresupuestoDetalle as Detalle,
  Version,
} from '../lib/api'
import { useContextoPresupuestos } from './Presupuestos'
import { useWorkspace } from '../workspace'

export function PresupuestoDetalle() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { onCambio } = useContextoPresupuestos()
  const [presupuesto, setPresupuesto] = useState<Detalle | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  const [nuevoCapituloEn, setNuevoCapituloEn] = useState<string | null | undefined>(undefined)
  const [nuevaPartidaEn, setNuevaPartidaEn] = useState<string | null>(null)
  const [midiendo, setMidiendo] = useState<Partida | null>(null)
  const [versiones, setVersiones] = useState<Version[]>([])
  const [guardandoPlantilla, setGuardandoPlantilla] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const [detalle, lineaVersiones] = await Promise.all([
        api.presupuestos.get(id),
        api.presupuestos.versiones(id),
      ])
      setPresupuesto(detalle)
      setVersiones(lineaVersiones)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  function cerrar() {
    navigate('/presupuestos')
  }

  if (error && !presupuesto) {
    return (
      <ModalPantalla title="Presupuesto" onClose={cerrar}>
        <ErrorNotice error={error} />
      </ModalPantalla>
    )
  }
  if (!presupuesto) return null

  async function cambiarEstado(estado: EstadoPresupuesto) {
    try {
      await api.presupuestos.update(id, { estado })
      await cargar()
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function sincronizar() {
    const { partidas_actualizadas } = await api.presupuestos.sincronizarPrecios(id)
    setAviso(
      partidas_actualizadas === 1
        ? '1 partida actualizada con el precio del cuadro.'
        : `${partidas_actualizadas} partidas actualizadas con el precio del cuadro.`,
    )
    await cargar()
  }

  async function eliminar() {
    if (!window.confirm(`¿Eliminar «${presupuesto!.nombre}» y todo su contenido?`)) return
    await api.presupuestos.remove(id)
    onCambio()
    cerrar()
  }

  async function crearVersion() {
    try {
      const nueva = await api.presupuestos.nuevaVersion(id)
      onCambio()
      navigate(`/presupuestos/${nueva.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const t = presupuesto.totales

  return (
    <ModalPantalla
      title={
        <>
          {presupuesto.nombre} <span className="table__code">{presupuesto.codigo}</span>
        </>
      }
      onClose={cerrar}
    >
      <div className="page-head">
        <div>
          <p className="page-lead" style={{ marginBottom: 0 }}>
            {presupuesto.emplazamiento && <>{presupuesto.emplazamiento} · </>}
            {presupuesto.fecha && <>{presupuesto.fecha} · </>}
            {presupuesto.precios_bloqueados && (
              <> <span className="badge">precios congelados</span></>
            )}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--sp-2)', alignItems: 'flex-start' }}>
          <select
            className="select"
            style={{ width: 'auto' }}
            value={presupuesto.estado}
            onChange={(e) => void cambiarEstado(e.target.value as EstadoPresupuesto)}
          >
            {Object.entries(ETIQUETA_ESTADO).map(([clave, etiqueta]) => (
              <option key={clave} value={clave}>
                {etiqueta}
              </option>
            ))}
          </select>
          <button className="btn btn--danger" onClick={() => void eliminar()}>
            Eliminar
          </button>
        </div>
      </div>

      <div className="barra-acciones">
        <span className="barra-acciones__grupo">
          <span className="barra-acciones__etiqueta">Descargar</span>
          {[
            ['presupuesto', 'Presupuesto'],
            ['mediciones', 'Mediciones'],
            ['descompuestos', 'Descompuestos'],
          ].map(([documento, etiqueta]) => (
            <button
              key={documento}
              className="btn btn--sm"
              onClick={() =>
                void descargar(
                  api.presupuestos.pdfUrl(id, documento),
                  `${presupuesto!.codigo}-${documento}.pdf`,
                  { abrir: true },
                ).catch((err) => setError(err instanceof Error ? err.message : String(err)))
              }
            >
              {etiqueta} PDF
            </button>
          ))}
          <button
            className="btn btn--sm"
            onClick={() =>
              void descargar(
                api.fiebdc.exportarUrl(id),
                `${presupuesto!.codigo}.bc3`,
              ).catch((err) => setError(err instanceof Error ? err.message : String(err)))
            }
          >
            BC3
          </button>
        </span>
        <span className="barra-acciones__grupo">
          <button className="btn btn--sm" onClick={() => void crearVersion()}>
            Nueva versión
          </button>
          <button className="btn btn--sm" onClick={() => setGuardandoPlantilla(true)}>
            Guardar como plantilla
          </button>
        </span>
      </div>

      {versiones.length > 1 && (
        <div className="versiones">
          <span className="barra-acciones__etiqueta">Versiones</span>
          {versiones.map((v) => (
            <span key={v.id} className="versiones__item">
              {v.id === id ? (
                <span className="chip chip--unitario">v{v.version}</span>
              ) : (
                <Link className="table__link" to={`/presupuestos/${v.id}`}>
                  v{v.version}
                </Link>
              )}
              {v.id !== id && (
                <Link className="versiones__comparar" to={`/presupuestos/${id}/comparar/${v.id}`}>
                  comparar
                </Link>
              )}
            </span>
          ))}
        </div>
      )}

      <ErrorNotice error={error} />
      {aviso && <div className="notice notice--ok">{aviso}</div>}

      {presupuesto.partidas_desactualizadas > 0 && (
        <div className="notice notice--aviso">
          <strong>{presupuesto.partidas_desactualizadas}</strong>{' '}
          {presupuesto.partidas_desactualizadas === 1 ? 'partida tiene' : 'partidas tienen'} un
          precio distinto del que hay ahora en el cuadro. Con los precios congelados no se
          actualizan solas.{' '}
          <button className="btn btn--sm" onClick={() => void sincronizar()}>
            Traer precios del cuadro
          </button>
        </div>
      )}

      <CamposLibres entidad="presupuesto" entidadId={id} />

      <div className="page-head" style={{ marginBottom: 'var(--sp-3)' }}>
        <h2 style={{ fontSize: 'var(--fs-xl)', fontWeight: 650 }}>Capítulos y partidas</h2>
        <button className="btn" onClick={() => setNuevoCapituloEn(null)}>
          Añadir capítulo
        </button>
      </div>

      <div className="table-wrap">
        {presupuesto.capitulos.length === 0 ? (
          <EmptyState title="Presupuesto vacío">
            Empieza creando un capítulo; dentro irán las partidas con su medición.
          </EmptyState>
        ) : (
          <table className="table tabla-presupuesto">
            <thead>
              <tr>
                <th>Código</th>
                <th>Descripción</th>
                <th className="table__num">Medición</th>
                <th className="table__num">Precio</th>
                <th className="table__num">Importe</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {presupuesto.capitulos.map((c) => (
                <FilasCapitulo
                  key={c.id}
                  nodo={c}
                  nivel={0}
                  onAnadirCapitulo={setNuevoCapituloEn}
                  onAnadirPartida={setNuevaPartidaEn}
                  onMedir={setMidiendo}
                  onCambio={cargar}
                />
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card resumen-totales">
        <Fila etiqueta="Presupuesto de ejecución material (PEM)" valor={t.pem} />
        <Fila
          etiqueta={`Gastos generales ${formatoImporte(presupuesto.gastos_generales)} %`}
          valor={t.gastos_generales}
          suave
        />
        <Fila
          etiqueta={`Beneficio industrial ${formatoImporte(presupuesto.beneficio_industrial)} %`}
          valor={t.beneficio_industrial}
          suave
        />
        <Fila etiqueta="Presupuesto de ejecución por contrata (sin IVA)" valor={t.pec_sin_iva} />
        <Fila
          etiqueta={
            presupuesto.inversion_sujeto_pasivo
              ? 'IVA — inversión del sujeto pasivo'
              : `IVA ${formatoImporte(t.porcentaje_iva, 0)} %`
          }
          valor={t.iva}
          suave
        />
        <Fila etiqueta="Total" valor={t.total} destacado />
      </div>

      {nuevoCapituloEn !== undefined && (
        <NuevoCapituloModal
          presupuestoId={id}
          parentId={nuevoCapituloEn}
          onClose={() => setNuevoCapituloEn(undefined)}
          onCreado={() => {
            setNuevoCapituloEn(undefined)
            void cargar()
          }}
        />
      )}

      {nuevaPartidaEn && (
        <NuevaPartidaModal
          capituloId={nuevaPartidaEn}
          onClose={() => setNuevaPartidaEn(null)}
          onCreada={() => {
            setNuevaPartidaEn(null)
            void cargar()
          }}
        />
      )}

      {midiendo && (
        <MedicionModal
          partida={midiendo}
          onClose={() => setMidiendo(null)}
          onCambio={cargar}
        />
      )}

      {guardandoPlantilla && (
        <GuardarPlantillaModal
          presupuestoId={id}
          nombreBase={presupuesto.nombre}
          onClose={() => setGuardandoPlantilla(false)}
          onGuardada={() => {
            setGuardandoPlantilla(false)
            setAviso('Plantilla creada. La tienes en la pestaña Plantillas.')
          }}
        />
      )}
    </ModalPantalla>
  )
}

function GuardarPlantillaModal({
  presupuestoId,
  nombreBase,
  onClose,
  onGuardada,
}: {
  presupuestoId: string
  nombreBase: string
  onClose: () => void
  onGuardada: () => void
}) {
  const [nombre, setNombre] = useState(`${nombreBase} — tipo`)
  const [tipoObra, setTipoObra] = useState('')
  const [conMediciones, setConMediciones] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    try {
      await api.presupuestos.guardarComoPlantilla(presupuestoId, {
        nombre,
        tipo_obra: tipoObra || null,
        con_mediciones: conMediciones,
      })
      onGuardada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title="Guardar como plantilla" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <p className="form-section__note">
          Se copian los capítulos y las partidas con sus precios. Lo reutilizable de un
          presupuesto es qué partidas lleva, no cuántos metros medía aquella obra.
        </p>
        <div className="form-grid">
          <Field label="Nombre de la plantilla">
            <input
              className="input"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              autoFocus
            />
          </Field>
          <Field label="Tipo de obra" hint="Sirve para agrupar y buscar plantillas">
            <input
              className="input"
              value={tipoObra}
              onChange={(e) => setTipoObra(e.target.value)}
              placeholder="rehabilitacion_fachada"
            />
          </Field>
        </div>
        <div style={{ marginTop: 'var(--sp-4)' }}>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={conMediciones}
              onChange={(e) => setConMediciones(e.target.checked)}
            />
            <span>Conservar también las mediciones</span>
          </label>
        </div>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={nombre.trim() === ''}
          onClick={() => void guardar()}
        >
          Guardar
        </button>
      </div>
    </Modal>
  )
}

function Fila({
  etiqueta,
  valor,
  suave,
  destacado,
}: {
  etiqueta: string
  valor: string
  suave?: boolean
  destacado?: boolean
}) {
  const clases = ['resumen-totales__fila']
  if (suave) clases.push('is-suave')
  if (destacado) clases.push('is-total')
  return (
    <div className={clases.join(' ')}>
      <span>{etiqueta}</span>
      <span className="resumen-totales__valor">{formatoImporte(valor)} €</span>
    </div>
  )
}

function FilasCapitulo({
  nodo,
  nivel,
  onAnadirCapitulo,
  onAnadirPartida,
  onMedir,
  onCambio,
}: {
  nodo: NodoCapitulo
  nivel: number
  onAnadirCapitulo: (parentId: string) => void
  onAnadirPartida: (capituloId: string) => void
  onMedir: (partida: Partida) => void
  onCambio: () => void
}) {
  async function eliminarCapitulo() {
    if (!window.confirm(`¿Eliminar el capítulo «${nodo.resumen}» y su contenido?`)) return
    await api.capitulos.remove(nodo.id)
    onCambio()
  }

  return (
    <>
      <tr className="fila-capitulo">
        <td className="table__code" style={{ paddingLeft: `calc(var(--sp-4) + ${nivel} * 20px)` }}>
          {nodo.codigo}
        </td>
        <td colSpan={3}>
          <strong>{nodo.resumen}</strong>
        </td>
        <td className="table__num">
          <strong>{formatoImporte(nodo.importe)}</strong>
        </td>
        <td className="table__actions">
          <button className="btn btn--sm" onClick={() => onAnadirPartida(nodo.id)}>
            + partida
          </button>{' '}
          <button className="btn btn--sm" onClick={() => onAnadirCapitulo(nodo.id)}>
            + subcapítulo
          </button>{' '}
          <button className="btn btn--sm btn--danger" onClick={() => void eliminarCapitulo()}>
            ×
          </button>
        </td>
      </tr>

      {nodo.partidas.map((partida) => (
        <FilaPartida
          key={partida.id}
          partida={partida}
          nivel={nivel + 1}
          onMedir={onMedir}
          onCambio={onCambio}
        />
      ))}

      {nodo.hijos.map((hijo) => (
        <FilasCapitulo
          key={hijo.id}
          nodo={hijo}
          nivel={nivel + 1}
          onAnadirCapitulo={onAnadirCapitulo}
          onAnadirPartida={onAnadirPartida}
          onMedir={onMedir}
          onCambio={onCambio}
        />
      ))}
    </>
  )
}

function FilaPartida({
  partida,
  nivel,
  onMedir,
  onCambio,
}: {
  partida: Partida
  nivel: number
  onMedir: (partida: Partida) => void
  onCambio: () => void
}) {
  async function eliminar() {
    if (!window.confirm(`¿Eliminar la partida «${partida.resumen}»?`)) return
    await api.partidas.remove(partida.id)
    onCambio()
  }

  return (
    <tr>
      <td className="table__code" style={{ paddingLeft: `calc(var(--sp-4) + ${nivel} * 20px)` }}>
        {partida.codigo}
      </td>
      <td>
        {partida.resumen}{' '}
        <span className="muted">({partida.unidad})</span>
        {partida.concepto_id === null && <span className="badge"> alzada</span>}
      </td>
      <td className="table__num">{formatoImporte(partida.medicion, 3)}</td>
      <td className="table__num">{formatoImporte(partida.precio)}</td>
      <td className="table__num">{formatoImporte(partida.importe)}</td>
      <td className="table__actions">
        <button className="btn btn--sm" onClick={() => onMedir(partida)}>
          Medir
        </button>{' '}
        <button className="btn btn--sm btn--danger" onClick={() => void eliminar()}>
          ×
        </button>
      </td>
    </tr>
  )
}

function NuevoCapituloModal({
  presupuestoId,
  parentId,
  onClose,
  onCreado,
}: {
  presupuestoId: string
  parentId: string | null
  onClose: () => void
  onCreado: () => void
}) {
  const [resumen, setResumen] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function guardar() {
    try {
      await api.presupuestos.addCapitulo(presupuestoId, { resumen, parent_id: parentId })
      onCreado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <Modal title={parentId ? 'Nuevo subcapítulo' : 'Nuevo capítulo'} onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Descripción" hint="El código se numera solo: 01, 01.01, 01.02…">
          <input
            className="input"
            value={resumen}
            onChange={(e) => setResumen(e.target.value)}
            autoFocus
          />
        </Field>
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button
          className="btn btn--primary"
          disabled={resumen.trim() === ''}
          onClick={() => void guardar()}
        >
          Crear
        </button>
      </div>
    </Modal>
  )
}

function NuevaPartidaModal({
  capituloId,
  onClose,
  onCreada,
}: {
  capituloId: string
  onClose: () => void
  onCreada: () => void
}) {
  const [modo, setModo] = useState<'cuadro' | 'alzada'>('cuadro')
  const [q, setQ] = useState('')
  const [candidatos, setCandidatos] = useState<Concepto[]>([])
  const [conceptoId, setConceptoId] = useState('')
  const [codigo, setCodigo] = useState('')
  const [resumen, setResumen] = useState('')
  const [unidad, setUnidad] = useState('ud')
  const [precio, setPrecio] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (modo !== 'cuadro') return
    const id = setTimeout(() => {
      void api.conceptos
        .list({ q: q || undefined, tipo: 'unitario', activo: true, limit: 50 })
        .then((page) => setCandidatos(page.items))
        .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
    }, 250)
    return () => clearTimeout(id)
  }, [q, modo])

  async function guardar() {
    setError(null)
    try {
      await api.capitulos.addPartida(
        capituloId,
        modo === 'cuadro'
          ? { concepto_id: conceptoId }
          : { codigo, resumen, unidad, precio: precio || '0' },
      )
      onCreada()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  const listo = modo === 'cuadro' ? conceptoId !== '' : resumen.trim() !== ''

  return (
    <Modal title="Nueva partida" onClose={onClose}>
      <div className="form-section">
        <ErrorNotice error={error} />
        <Field label="Origen">
          <select
            className="select"
            value={modo}
            onChange={(e) => setModo(e.target.value as 'cuadro' | 'alzada')}
          >
            <option value="cuadro">Del cuadro de precios</option>
            <option value="alzada">Partida alzada (sin concepto)</option>
          </select>
        </Field>

        {modo === 'cuadro' ? (
          <>
            <div style={{ marginTop: 'var(--sp-4)' }}>
              <Field label="Buscar unitario">
                <input
                  className="input"
                  placeholder="Código o descripción…"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  autoFocus
                />
              </Field>
            </div>
            <div className="lista-seleccion">
              {candidatos.length === 0 ? (
                <div className="muted" style={{ padding: 'var(--sp-3)' }}>
                  No hay unitarios en el cuadro de precios
                </div>
              ) : (
                candidatos.map((c) => (
                  <button
                    key={c.id}
                    className={
                      conceptoId === c.id
                        ? 'lista-seleccion__item is-activo'
                        : 'lista-seleccion__item'
                    }
                    onClick={() => setConceptoId(c.id)}
                  >
                    <span className="table__code">{c.codigo}</span>
                    <span className="lista-seleccion__texto">{c.resumen}</span>
                    <span className="chip chip--unitario">unitario</span>
                    <span className="table__num">
                      {formatoImporte(c.precio)} €/{c.unidad}
                    </span>
                  </button>
                ))
              )}
            </div>
            <p className="field__hint" style={{ marginTop: 'var(--sp-2)' }}>
              Se copian código, descripción, unidad y precio. La partida conserva esa copia
              aunque el cuadro cambie después.
            </p>
          </>
        ) : (
          <div className="form-grid" style={{ marginTop: 'var(--sp-4)' }}>
            <Field label="Código">
              <input className="input" value={codigo} onChange={(e) => setCodigo(e.target.value)} />
            </Field>
            <Field label="Descripción">
              <input
                className="input"
                value={resumen}
                onChange={(e) => setResumen(e.target.value)}
              />
            </Field>
            <Field label="Unidad">
              <input className="input" value={unidad} onChange={(e) => setUnidad(e.target.value)} />
            </Field>
            <Field label="Precio">
              <input
                className="input"
                type="number"
                step="0.01"
                value={precio}
                onChange={(e) => setPrecio(e.target.value)}
              />
            </Field>
          </div>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        <button className="btn btn--primary" disabled={!listo} onClick={() => void guardar()}>
          Añadir
        </button>
      </div>
    </Modal>
  )
}

function MedicionModal({
  partida,
  onClose,
  onCambio,
}: {
  partida: Partida
  onClose: () => void
  onCambio: () => void
}) {
  const { modules } = useWorkspace()
  const iaActiva = modules.some((m) => m.code === 'ia' && m.is_active)
  const [detalle, setDetalle] = useState<Awaited<
    ReturnType<typeof api.partidas.get>
  > | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [leyendoPlano, setLeyendoPlano] = useState(false)

  const recargar = useCallback(async () => {
    try {
      setDetalle(await api.partidas.get(partida.id))
      onCambio()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [partida.id, onCambio])

  useEffect(() => {
    void api.partidas
      .get(partida.id)
      .then(setDetalle)
      .catch((err) => setError(err instanceof Error ? err.message : 'Error desconocido'))
  }, [partida.id])

  async function anadir() {
    await api.partidas.addLinea(partida.id, { comentario: '', uds: '1' })
    await recargar()
  }

  return (
    <Modal title={`Medición · ${partida.codigo}`} onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          {partida.resumen}. El parcial es el producto de lo que esté informado: una línea con
          solo unidades mide esas unidades. Un valor negativo deduce, que es como se descuentan
          los huecos.
        </p>
        <ErrorNotice error={error} />

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Comentario</th>
                <th className="table__num">Uds</th>
                <th className="table__num">Longitud</th>
                <th className="table__num">Anchura</th>
                <th className="table__num">Altura</th>
                <th className="table__num">Parcial</th>
                <th className="table__actions" />
              </tr>
            </thead>
            <tbody>
              {(detalle?.lineas ?? []).map((linea) => (
                <FilaMedicion key={linea.id} linea={linea} onCambio={recargar} />
              ))}
            </tbody>
            <tfoot>
              <tr className="fila-total">
                <td colSpan={5} className="table__num total-label">
                  Medición total
                </td>
                <td className="table__num">
                  <strong>{formatoImporte(detalle?.medicion ?? '0', 3)}</strong>
                </td>
                <td />
              </tr>
              <tr>
                <td colSpan={5} className="table__num total-label">
                  × {formatoImporte(detalle?.precio ?? '0')} €/{partida.unidad}
                </td>
                <td className="table__num">
                  <strong>{formatoImporte(detalle?.importe ?? '0')} €</strong>
                </td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>

        <div style={{ display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-3)' }}>
          <button className="btn" onClick={() => void anadir()}>
            Añadir línea
          </button>
          {iaActiva && (
            <button className="btn" onClick={() => setLeyendoPlano(true)}>
              Leer plano (IA)
            </button>
          )}
        </div>
      </div>

      <CamposLibres entidad="partida" entidadId={partida.id} />

      <div className="form-actions">
        <button className="btn btn--primary" onClick={onClose}>
          Hecho
        </button>
      </div>

      {leyendoPlano && (
        <LeerPlanoModal
          partida={partida}
          onClose={() => setLeyendoPlano(false)}
          onAplicado={() => {
            setLeyendoPlano(false)
            void recargar()
          }}
        />
      )}
    </Modal>
  )
}

function LeerPlanoModal({
  partida,
  onClose,
  onAplicado,
}: {
  partida: Partida
  onClose: () => void
  onAplicado: () => void
}) {
  const [lectura, setLectura] = useState<LecturaPlanoDetalle | null>(null)
  const [lineas, setLineas] = useState<(LineaSugerida & { incluir: boolean })[]>([])
  const [error, setError] = useState<string | null>(null)
  const [leyendo, setLeyendo] = useState(false)
  const [aplicando, setAplicando] = useState(false)

  async function elegir(elegido: File | null) {
    setLectura(null)
    setError(null)
    if (!elegido) return

    setLeyendo(true)
    try {
      const resultado = await api.ia.mediciones.leer(partida.id, elegido)
      setLectura(resultado)
      setLineas(resultado.lineas.map((l) => ({ ...l, incluir: true })))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLeyendo(false)
    }
  }

  function editarLinea(
    indice: number,
    cambios: Partial<LineaSugerida & { incluir: boolean }>,
  ) {
    setLineas((actual) => actual.map((l, i) => (i !== indice ? l : { ...l, ...cambios })))
  }

  async function aplicar() {
    if (!lectura) return
    setAplicando(true)
    setError(null)
    try {
      await api.ia.mediciones.aplicar(
        lectura.id,
        lineas
          .filter((l) => l.incluir)
          .map(({ comentario, uds, longitud, anchura, altura }) => ({
            comentario,
            uds,
            longitud,
            anchura,
            altura,
          })),
      )
      onAplicado()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
      setAplicando(false)
    }
  }

  return (
    <Modal title={`Leer plano · ${partida.codigo}`} onClose={onClose}>
      <div className="form-section">
        <p className="form-section__note">
          Sube un plano acotado (PDF, PNG, JPEG o WebP) para la partida «{partida.resumen}».
          Gemini propone líneas de medición a partir de las cotas del plano; nada se escribe
          hasta que revises y confirmes abajo.
        </p>
        <ErrorNotice error={error} />

        {!lectura && (
          <Field label="Plano">
            <input
              className="input"
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              onChange={(e) => void elegir(e.target.files?.[0] ?? null)}
            />
          </Field>
        )}
        {leyendo && <p className="muted">Analizando el plano con Gemini…</p>}

        {lectura && (
          <>
            {lectura.observaciones && (
              <div className="notice notice--aviso">{lectura.observaciones}</div>
            )}
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th />
                    <th>Comentario</th>
                    <th className="table__num">Uds</th>
                    <th className="table__num">Longitud</th>
                    <th className="table__num">Anchura</th>
                    <th className="table__num">Altura</th>
                    <th className="table__num">Parcial</th>
                  </tr>
                </thead>
                <tbody>
                  {lineas.map((linea, i) => (
                    <tr key={i}>
                      <td>
                        <input
                          type="checkbox"
                          checked={linea.incluir}
                          onChange={(e) => editarLinea(i, { incluir: e.target.checked })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          value={linea.comentario ?? ''}
                          onChange={(e) => editarLinea(i, { comentario: e.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '70px' }}
                          value={linea.uds ?? ''}
                          onChange={(e) => editarLinea(i, { uds: e.target.value || null })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '70px' }}
                          value={linea.longitud ?? ''}
                          onChange={(e) => editarLinea(i, { longitud: e.target.value || null })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '70px' }}
                          value={linea.anchura ?? ''}
                          onChange={(e) => editarLinea(i, { anchura: e.target.value || null })}
                        />
                      </td>
                      <td>
                        <input
                          className="input"
                          style={{ width: '70px' }}
                          value={linea.altura ?? ''}
                          onChange={(e) => editarLinea(i, { altura: e.target.value || null })}
                        />
                      </td>
                      <td className="table__num muted">{formatoImporte(linea.parcial, 3)}</td>
                    </tr>
                  ))}
                  {lineas.length === 0 && (
                    <tr>
                      <td colSpan={7} className="muted">
                        Gemini no ha propuesto ninguna línea para esta partida
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
      <div className="form-actions">
        <button className="btn" onClick={onClose}>
          Cancelar
        </button>
        {lectura && (
          <button
            className="btn btn--primary"
            disabled={aplicando || lineas.every((l) => !l.incluir)}
            onClick={() => void aplicar()}
          >
            {aplicando ? 'Aplicando…' : 'Aplicar seleccionadas'}
          </button>
        )}
      </div>
    </Modal>
  )
}

function FilaMedicion({
  linea,
  onCambio,
}: {
  linea: import('../lib/api').LineaMedicion
  onCambio: () => void
}) {
  const [valores, setValores] = useState({
    comentario: linea.comentario ?? '',
    uds: linea.uds ?? '',
    longitud: linea.longitud ?? '',
    anchura: linea.anchura ?? '',
    altura: linea.altura ?? '',
  })

  // Se guarda al salir del campo: cada guardado recalcula la partida y, con
  // ella, todos los totales del presupuesto.
  async function guardar() {
    await api.mediciones.update(linea.id, {
      comentario: valores.comentario || null,
      uds: valores.uds === '' ? null : valores.uds,
      longitud: valores.longitud === '' ? null : valores.longitud,
      anchura: valores.anchura === '' ? null : valores.anchura,
      altura: valores.altura === '' ? null : valores.altura,
    })
    onCambio()
  }

  async function eliminar() {
    await api.mediciones.remove(linea.id)
    onCambio()
  }

  const campo = (clave: keyof typeof valores) => (
    <input
      className="input input--celda"
      type={clave === 'comentario' ? 'text' : 'number'}
      step="0.001"
      value={valores[clave]}
      onChange={(e) => setValores((v) => ({ ...v, [clave]: e.target.value }))}
      onBlur={() => void guardar()}
    />
  )

  return (
    <tr>
      <td>
        <input
          className="input input--celda input--texto"
          value={valores.comentario}
          onChange={(e) => setValores((v) => ({ ...v, comentario: e.target.value }))}
          onBlur={() => void guardar()}
          placeholder="—"
        />
      </td>
      <td className="table__num">{campo('uds')}</td>
      <td className="table__num">{campo('longitud')}</td>
      <td className="table__num">{campo('anchura')}</td>
      <td className="table__num">{campo('altura')}</td>
      <td className="table__num">
        <strong>{formatoImporte(linea.parcial, 3)}</strong>
      </td>
      <td className="table__actions">
        <button className="btn btn--sm btn--danger" onClick={() => void eliminar()}>
          ×
        </button>
      </td>
    </tr>
  )
}
