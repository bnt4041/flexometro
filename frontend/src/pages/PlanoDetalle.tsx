import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Circle,
  Hand,
  Layers,
  Minus,
  Plus,
  Ruler,
  MousePointerClick,
  Sparkles,
  Square,
  StickyNote,
  Trash2,
  Waypoints,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'

import { LienzoPlano } from '../components/LienzoPlano'
import type { Herramienta } from '../components/LienzoPlano'
import { ErrorNotice, Field, Modal, ModalPantalla, formatoImporte } from '../components/ui'
import { api } from '../lib/api'
import type {
  CapaPlano,
  ElementoPlano,
  LecturaIaPlano,
  PlanoDetalle as Detalle,
  PuntoPlano,
} from '../lib/api'
import { useToast } from '../toast'

const HERRAMIENTAS: { id: Herramienta; etiqueta: string; icono: typeof Hand; soloDxf?: boolean }[] = [
  { id: 'mano', etiqueta: 'Seleccionar', icono: Hand },
  { id: 'entidad', etiqueta: 'Medir una entidad del plano', icono: MousePointerClick, soloDxf: true },
  { id: 'calibrar', etiqueta: 'Calibrar con una cota', icono: Ruler },
  { id: 'longitud', etiqueta: 'Medir longitud', icono: Waypoints },
  { id: 'area', etiqueta: 'Medir área', icono: Square },
  { id: 'conteo', etiqueta: 'Contar', icono: Circle },
  { id: 'auxiliar', etiqueta: 'Línea auxiliar', icono: Minus },
  { id: 'nota', etiqueta: 'Nota', icono: StickyNote },
]

const AYUDA: Record<Herramienta, string> = {
  mano: 'Pincha un elemento para verlo o borrarlo.',
  entidad:
    'Pincha una línea del plano y se mide entera, con su geometría exacta. No hay que ir vértice a vértice.',
  calibrar: 'Pincha los dos extremos de una cota que conozcas y teclea cuánto mide.',
  longitud: 'Pincha los vértices. Doble clic o Enter para cerrar, Esc para descartar.',
  area: 'Pincha el contorno. Doble clic o Enter para cerrar; se cierra solo.',
  conteo: 'Un clic por unidad. Doble clic o Enter para cerrar.',
  auxiliar: 'Dos puntos. No mide: sirve para alinear y replantear.',
  nota: 'Pincha dónde va y escribe el texto.',
}

export function PlanoDetalle() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { notificar } = useToast()

  const [plano, setPlano] = useState<Detalle | null>(null)
  const [hojaId, setHojaId] = useState<string | null>(null)
  const [elementos, setElementos] = useState<ElementoPlano[]>([])
  const [herramienta, setHerramienta] = useState<Herramienta>('mano')
  const [capaActiva, setCapaActiva] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [seleccionado, setSeleccionado] = useState<string | null>(null)
  const [pendiente, setPendiente] = useState<{ tipo: Herramienta; puntos: PuntoPlano[] } | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [lectura, setLectura] = useState<LecturaIaPlano | null>(null)
  const [leyendo, setLeyendo] = useState(false)
  // Cuando la IA ha leído una cota, su valor queda cargado: al pinchar los dos
  // extremos se calibra directamente, sin volver a teclear cuánto mide.
  const [cotaPrefijada, setCotaPrefijada] = useState<string | null>(null)

  const cargar = useCallback(async () => {
    if (!id) return
    try {
      const detalle = await api.planos.get(id)
      setPlano(detalle)
      setHojaId((actual) => actual ?? detalle.hojas[0]?.id ?? null)
      setCapaActiva((actual) => actual ?? detalle.capas[0]?.id ?? null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [id])

  useEffect(() => {
    void cargar()
  }, [cargar])

  const cargarElementos = useCallback(async () => {
    if (!hojaId) return
    try {
      setElementos(await api.planos.elementos.list(hojaId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }, [hojaId])

  useEffect(() => {
    void cargarElementos()
  }, [cargarElementos])

  const hoja = useMemo(
    () => plano?.hojas.find((h) => h.id === hojaId) ?? null,
    [plano, hojaId],
  )
  const calibrada = hoja?.metros_por_unidad != null
  const esVectorial = plano?.origen === 'dxf'

  async function alTerminar(tipo: Herramienta, puntos: PuntoPlano[]) {
    if (!hoja) return
    // Calibrar y anotar piden un dato más antes de poder guardarse; el resto
    // se guarda directamente.
    if (tipo === 'calibrar') {
      if (cotaPrefijada) {
        const valor = cotaPrefijada
        setCotaPrefijada(null)
        await calibrar(puntos, valor)
        return
      }
      setPendiente({ tipo, puntos })
      return
    }
    if (tipo === 'nota') {
      setPendiente({ tipo, puntos })
      return
    }
    await guardar(tipo, puntos, null)
  }

  async function guardar(tipo: Herramienta, puntos: PuntoPlano[], texto: string | null) {
    if (!hoja) return
    try {
      await api.planos.elementos.create(hoja.id, {
        tipo: tipo as ElementoPlano['tipo'],
        geometria: puntos,
        capa_id: capaActiva,
        texto,
      })
      await cargarElementos()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function calibrar(puntos: PuntoPlano[], distancia: string) {
    if (!hoja) return
    try {
      await api.planos.calibrar(hoja.id, puntos[0], puntos[1], distancia)
      await cargar()
      await cargarElementos()
      notificar('Hoja calibrada. Se han recalculado las mediciones que había.')
      setHerramienta('mano')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function leerConIa() {
    if (!hoja) return
    setLeyendo(true)
    setError(null)
    try {
      setLectura(await api.planos.leerConIa(hoja.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setLeyendo(false)
    }
  }

  async function calibrarPorEscala(denominador: number) {
    if (!hoja) return
    try {
      await api.planos.calibrarPorEscala(hoja.id, denominador)
      setLectura(null)
      await cargar()
      await cargarElementos()
      notificar(`Calibrado a 1:${denominador}. Escala exacta, sin estimar nada.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function borrar(elementoId: string) {
    try {
      await api.planos.elementos.remove(elementoId)
      setSeleccionado(null)
      await cargarElementos()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  if (!plano || !hoja) {
    return (
      <ModalPantalla title="Plano" onClose={() => navigate('/planos')}>
        <ErrorNotice error={error} />
        {!error && <p className="muted">Cargando…</p>}
      </ModalPantalla>
    )
  }

  const mediciones = elementos.filter((e) =>
    ['longitud', 'area', 'conteo'].includes(e.tipo),
  )

  return (
    <ModalPantalla
      title={`${plano.codigo} · ${plano.nombre}`}
      onClose={() => navigate('/planos')}
    >
      <ErrorNotice error={error} />

      <div className="plano">
        <div className="plano__barra">
          {HERRAMIENTAS.filter((h) => !h.soloDxf || esVectorial).map(({ id: hid, etiqueta, icono: Icono }) => (
            <button
              key={hid}
              type="button"
              title={etiqueta}
              aria-label={etiqueta}
              aria-pressed={herramienta === hid}
              className={`btn btn--sm${herramienta === hid ? ' btn--primary' : ''}`}
              // Sin escala no hay medición posible: ofrecer las herramientas
              // de medir antes de calibrar solo produce elementos sin valor.
              disabled={!calibrada && ['longitud', 'area', 'entidad'].includes(hid)}
              onClick={() => setHerramienta(hid)}
            >
              <Icono size={14} aria-hidden="true" />
            </button>
          ))}

          <span className="plano__separador" />

          {plano.hojas.length > 1 && (
            <select
              className="select"
              style={{ width: 'auto' }}
              value={hoja.id}
              onChange={(e) => {
                setHojaId(e.target.value)
                setSeleccionado(null)
              }}
            >
              {plano.hojas.map((h) => (
                <option key={h.id} value={h.id}>
                  Hoja {h.numero}
                  {h.metros_por_unidad == null ? ' (sin calibrar)' : ''}
                </option>
              ))}
            </select>
          )}

          {!esVectorial && (
            <button
              type="button"
              className="btn btn--sm"
              disabled={leyendo}
              onClick={() => void leerConIa()}
            >
              <Sparkles size={14} aria-hidden="true" />{' '}
              {leyendo ? 'Leyendo…' : 'Leer con IA'}
            </button>
          )}

          <button
            type="button"
            className="btn btn--sm"
            aria-label="Alejar"
            onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}
          >
            <ZoomOut size={14} aria-hidden="true" />
          </button>
          <span className="muted">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            className="btn btn--sm"
            aria-label="Ampliar"
            onClick={() => setZoom((z) => Math.min(8, z + 0.25))}
          >
            <ZoomIn size={14} aria-hidden="true" />
          </button>
        </div>

        <p className="plano__ayuda">
          {cotaPrefijada && (
            <strong>
              Cota cargada: {cotaPrefijada} m. Pincha sus dos extremos y se calibra.{' '}
            </strong>
          )}
          {!calibrada && (
            <strong>
              Esta hoja no está calibrada, así que todavía no se puede medir en metros.{' '}
            </strong>
          )}
          {AYUDA[herramienta]}
        </p>

        <div className="plano__cuerpo">
          <div className="plano__visor">
            <LienzoPlano
              rutaArchivo={api.planos.rutaArchivo(plano.id)}
              esPdf={plano.origen === 'pdf'}
              esVectorial={esVectorial}
              hoja={hoja}
              capas={plano.capas}
              elementos={elementos}
              herramienta={herramienta}
              zoom={zoom}
              seleccionado={seleccionado}
              onSeleccionar={setSeleccionado}
              onTerminar={(t, p) => void alTerminar(t, p)}
              onEntidad={(puntos, cerrado) =>
                void guardar(cerrado ? 'area' : 'longitud', puntos, 'Entidad del plano')
              }
            />
          </div>

          <aside className="plano__panel">
            <Capas
              plano={plano}
              activa={capaActiva}
              onActiva={setCapaActiva}
              onCambio={cargar}
              onError={setError}
            />

            <section className="form-section">
              <h2 className="form-section__title">
                <Layers size={14} aria-hidden="true" /> Mediciones
              </h2>
              {mediciones.length === 0 ? (
                <p className="muted">Nada medido todavía en esta hoja.</p>
              ) : (
                <ul className="lista">
                  {mediciones.map((m) => (
                    <li
                      key={m.id}
                      className={m.id === seleccionado ? 'plano__medicion--activa' : undefined}
                    >
                      <button
                        type="button"
                        className="btn-enlace"
                        onClick={() => setSeleccionado(m.id)}
                      >
                        {m.valor == null
                          ? 'sin calibrar'
                          : `${formatoImporte(m.valor, m.tipo === 'conteo' ? 0 : 2)} ${m.unidad}`}
                      </button>
                      {m.linea_medicion_id && <span className="badge">en presupuesto</span>}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {seleccionado && (
              <div className="form-actions">
                <button
                  type="button"
                  className="btn btn--sm btn--danger"
                  onClick={() => void borrar(seleccionado)}
                >
                  <Trash2 size={14} aria-hidden="true" /> Borrar
                </button>
              </div>
            )}
          </aside>
        </div>
      </div>

      {pendiente?.tipo === 'calibrar' && (
        <PedirCota
          onCerrar={() => setPendiente(null)}
          onAceptar={(d) => {
            const puntos = pendiente.puntos
            setPendiente(null)
            void calibrar(puntos, d)
          }}
        />
      )}
      {lectura && (
        <LecturaIa
          lectura={lectura}
          onCerrar={() => setLectura(null)}
          onEscala={(d) => void calibrarPorEscala(d)}
          onCota={(metros) => {
            setCotaPrefijada(metros)
            setHerramienta('calibrar')
            setLectura(null)
          }}
        />
      )}
      {pendiente?.tipo === 'nota' && (
        <PedirTexto
          onCerrar={() => setPendiente(null)}
          onAceptar={(t) => {
            const puntos = pendiente.puntos
            setPendiente(null)
            void guardar('nota', puntos, t)
          }}
        />
      )}
    </ModalPantalla>
  )
}

function Capas({
  plano,
  activa,
  onActiva,
  onCambio,
  onError,
}: {
  plano: Detalle
  activa: string | null
  onActiva: (id: string) => void
  onCambio: () => Promise<void>
  onError: (m: string) => void
}) {
  const [nueva, setNueva] = useState('')

  async function cambiar(capa: CapaPlano, cambios: Partial<CapaPlano>) {
    try {
      await api.planos.capas.update(capa.id, { ...capa, ...cambios })
      await onCambio()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function crear() {
    if (!nueva.trim()) return
    try {
      await api.planos.capas.create(plano.id, { nombre: nueva, orden: plano.capas.length })
      setNueva('')
      await onCambio()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  return (
    <section className="form-section">
      <h2 className="form-section__title">Capas</h2>
      <ul className="lista">
        {plano.capas.map((capa) => (
          <li key={capa.id} className="plano__capa">
            <input
              type="checkbox"
              checked={capa.visible}
              aria-label={`Ver ${capa.nombre}`}
              onChange={(e) => void cambiar(capa, { visible: e.target.checked })}
            />
            <input
              type="color"
              value={capa.color}
              aria-label={`Color de ${capa.nombre}`}
              onChange={(e) => void cambiar(capa, { color: e.target.value })}
            />
            <button
              type="button"
              className={capa.id === activa ? 'btn-enlace plano__capa--activa' : 'btn-enlace'}
              onClick={() => onActiva(capa.id)}
            >
              {capa.nombre}
            </button>
          </li>
        ))}
      </ul>
      <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
        <input
          className="input"
          value={nueva}
          placeholder="Nueva capa"
          onChange={(e) => setNueva(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && void crear()}
        />
        <button type="button" className="btn btn--sm" onClick={() => void crear()}>
          <Plus size={14} aria-hidden="true" />
        </button>
      </div>
    </section>
  )
}

function PedirCota({
  onCerrar,
  onAceptar,
}: {
  onCerrar: () => void
  onAceptar: (distancia: string) => void
}) {
  const [valor, setValor] = useState('')
  const numero = Number(valor.replace(',', '.'))
  const valido = Number.isFinite(numero) && numero > 0

  return (
    <Modal title="¿Cuánto mide esa cota?" onClose={onCerrar}>
      <p className="muted">
        En metros. De aquí sale la escala de toda la hoja, así que conviene pinchar una
        cota larga: cuanto más corta, más se nota el error de un par de píxeles.
      </p>
      <Field label="Distancia real (m)">
        <input
          className="input"
          value={valor}
          autoFocus
          placeholder="Por ejemplo: 5,40"
          onChange={(e) => setValor(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && valido && onAceptar(String(numero))}
        />
      </Field>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!valido}
          onClick={() => onAceptar(String(numero))}
        >
          Calibrar
        </button>
      </div>
    </Modal>
  )
}

function PedirTexto({
  onCerrar,
  onAceptar,
}: {
  onCerrar: () => void
  onAceptar: (texto: string) => void
}) {
  const [texto, setTexto] = useState('')
  return (
    <Modal title="Nota" onClose={onCerrar}>
      <Field label="Texto">
        <textarea
          className="input"
          rows={4}
          value={texto}
          autoFocus
          onChange={(e) => setTexto(e.target.value)}
        />
      </Field>
      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={!texto.trim()}
          onClick={() => onAceptar(texto)}
        >
          Guardar
        </button>
      </div>
    </Modal>
  )
}


function LecturaIa({
  lectura,
  onCerrar,
  onEscala,
  onCota,
}: {
  lectura: LecturaIaPlano
  onCerrar: () => void
  onEscala: (denominador: number) => void
  onCota: (metros: string) => void
}) {
  return (
    <Modal title="Lo que la IA ha leído del plano" onClose={onCerrar}>
      {lectura.resumen && <p>{lectura.resumen}</p>}

      {lectura.escala_impresa !== null && lectura.escala_aplicable && (
        <section className="form-section">
          <h2 className="form-section__title">
            Escala impresa: 1:{lectura.escala_impresa}
            {lectura.escala_texto && ` («${lectura.escala_texto}»)`}
          </h2>
          <p className="muted">
            Con esto la calibración es <strong>exacta</strong>: la cuenta sale de la
            geometría del papel, no de estimar píxeles. Es la mejor opción si el
            cajetín dice la verdad y el PDF no se ha reescalado al imprimirlo.
          </p>
          <div className="form-actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => onEscala(lectura.escala_impresa!)}
            >
              Calibrar a 1:{lectura.escala_impresa}
            </button>
          </div>
        </section>
      )}

      {lectura.escala_impresa !== null && !lectura.escala_aplicable && (
        <section className="form-section">
          <h2 className="form-section__title">Escala impresa: 1:{lectura.escala_impresa}</h2>
          <p className="muted">
            No se puede aplicar en una imagen: un píxel no mide nada sin saber a qué
            resolución se escaneó. Usa una de las cotas de abajo.
          </p>
        </section>
      )}

      {lectura.cotas.length > 0 && (
        <section className="form-section">
          <h2 className="form-section__title">Cotas que ha leído</h2>
          <p className="muted">
            El valor es de fiar porque está escrito; dónde empieza y acaba, no. Elige
            una y pincha sus dos extremos.
          </p>
          <ul className="lista">
            {lectura.cotas.map((c, i) => (
              <li key={i}>
                <button type="button" className="btn-enlace" onClick={() => onCota(c.metros)}>
                  {c.texto} → {c.metros} m
                </button>
                {c.donde && <span className="muted"> · {c.donde}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {lectura.avisos.length > 0 && (
        <section className="form-section">
          <h2 className="form-section__title">Avisos</h2>
          <ul className="lista">
            {lectura.avisos.map((a, i) => (
              <li key={i} className="muted">
                {a}
              </li>
            ))}
          </ul>
        </section>
      )}

      {lectura.escala_impresa === null && lectura.cotas.length === 0 && (
        <p className="muted">
          No ha encontrado ni escala ni cotas escritas. Calíbralo a mano pinchando una
          medida que conozcas.
        </p>
      )}

      <div className="form-actions">
        <button type="button" className="btn" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </Modal>
  )
}
