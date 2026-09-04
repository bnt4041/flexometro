import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, FileImage, FileText, Trash2, Upload, Waypoints } from 'lucide-react'

import { VisorPlano } from './VisorPlano'
import { EmptyState, ErrorNotice } from './ui'
import { api } from '../lib/api'
import type { Partida, Plano } from '../lib/api'
import { leerHojas } from '../lib/hojasPlano'
import { useToast } from '../toast'

const ADMITIDOS = '.pdf,.png,.jpg,.jpeg,.webp,.dxf'

const ICONO_ORIGEN: Record<Plano['origen'], typeof FileText> = {
  pdf: FileText,
  imagen: FileImage,
  dxf: Waypoints,
}

/** El layout de planos del objeto: N planos, uno visible a la vez.
 *
 *  No es un apartado aparte ni una biblioteca: son *los planos de este
 *  presupuesto*, y por eso vive como una pestaña más de su ficha. Soltar un
 *  fichero encima lo sube y lo abre — sin formulario de por medio, porque el
 *  nombre sale del propio fichero y todo lo demás lo averigua el servidor (un
 *  DXF trae su geometría y sus unidades; un PDF o una foto los revisa la IA
 *  nada más subirlos).
 *
 *  Con `partida` puesta, cada medición del plano puede irse a esa partida:
 *  es lo que convierte «un plano guardado» en «la medición del presupuesto». */
export function LayoutPlanos({
  presupuestoId,
  partida,
  onAplicado,
  onVolver,
  irA,
  onIrAConsumido,
}: {
  presupuestoId: string
  partida?: Partida | null
  onAplicado?: () => void
  /** Vuelve a la pestaña de Datos, con la partida que ya estaba
   *  seleccionada — se llega a Planos SIEMPRE desde ahí (el botón «Planos»
   *  de Mediciones), así que aquí dentro conviene un botón que lo diga
   *  explícitamente: la pestaña «Datos» de arriba también sirve, pero es un
   *  texto gris más entre seis pestañas y no se lee como «volver». Sin
   *  `partida` (se entró por la biblioteca de planos, no desde una
   *  partida) no hay a dónde volver que tenga más sentido que la propia
   *  pestaña, así que no se ofrece. */
  onVolver?: () => void
  /** A qué plano (y, si se sabe, qué hoja) ir en vez de al primero de la
   *  lista — se rellena al venir de Mediciones con una línea concreta. */
  irA?: { planoId: string; hojaId?: string }
  /** Avisa de que `irA` ya se ha aplicado, para que quien lo puso no lo
   *  vuelva a forzar en el siguiente repintado (p. ej. tras cambiar de
   *  plano a mano dentro de esta misma pestaña). */
  onIrAConsumido?: () => void
}) {
  const { notificar } = useToast()
  const [planos, setPlanos] = useState<Plano[]>([])
  const [planoId, setPlanoId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [subiendo, setSubiendo] = useState(false)
  const [arrastrando, setArrastrando] = useState(false)
  // Un DXF llega ya con su geometría y sus unidades; un PDF o una foto no, así
  // que a esos los revisa la IA sola nada más subirlos.
  const [revisarConIa, setRevisarConIa] = useState(false)
  const [hojaObjetivo, setHojaObjetivo] = useState<string | undefined>(undefined)
  const inputRef = useRef<HTMLInputElement>(null)

  // Salta al plano (y hoja) que traiga `irA`, aunque no sea el primero de la
  // lista. `VisorPlano` pide el detalle por `planoId` directamente, así que
  // no hace falta esperar a que `planos` esté cargado para poder ponerlo.
  useEffect(() => {
    if (!irA) return
    setPlanoId(irA.planoId)
    setHojaObjetivo(irA.hojaId)
    onIrAConsumido?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [irA])

  const cargar = useCallback(async () => {
    setCargando(true)
    try {
      const lista = await api.planos.list({ presupuesto_id: presupuestoId })
      setPlanos(lista)
      setPlanoId((actual) => actual ?? lista[0]?.id ?? null)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setCargando(false)
    }
  }, [presupuestoId])

  useEffect(() => {
    void cargar()
  }, [cargar])

  // Las líneas que ya tiene la partida, para distinguir «esto ya está en esta
  // partida» de «esto se llevó a otra» sin ampliar el backend para eso.
  const [idsLineas, setIdsLineas] = useState<Set<string>>(new Set())
  const partidaId = partida?.id

  const cargarLineas = useCallback(async () => {
    if (!partidaId) {
      setIdsLineas(new Set())
      return
    }
    try {
      const detalle = await api.partidas.get(partidaId)
      setIdsLineas(new Set(detalle.lineas.map((l) => l.id)))
    } catch {
      // Sin esto solo se pierde el matiz del distintivo, no la medición.
      setIdsLineas(new Set())
    }
  }, [partidaId])

  useEffect(() => {
    void cargarLineas()
  }, [cargarLineas])

  async function borrarPlano() {
    const plano = planos.find((p) => p.id === planoId)
    if (!plano) return
    if (
      !window.confirm(
        `¿Borrar «${plano.nombre}» (${plano.codigo}) de este presupuesto?\n\n` +
          'Se va con todas sus hojas y con lo medido encima. Lo que ya se llevó a una ' +
          'partida sigue contando en el presupuesto: se pierde la marca sobre el plano de ' +
          'dónde salió el número, no el número.',
      )
    ) {
      return
    }
    setError(null)
    try {
      await api.planos.remove(plano.id)
      const quedan = planos.filter((p) => p.id !== plano.id)
      setPlanos(quedan)
      setPlanoId(quedan[0]?.id ?? null)
      notificar(`${plano.codigo} borrado`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    }
  }

  async function subir(fichero: File) {
    setSubiendo(true)
    setError(null)
    try {
      const hojas = await leerHojas(fichero)
      const nombre = fichero.name.replace(/\.[^.]+$/, '')
      const plano = await api.planos.subir({ nombre, presupuesto_id: presupuestoId }, fichero, hojas)
      setPlanos((actuales) => [...actuales, plano])
      setPlanoId(plano.id)
      setRevisarConIa(plano.origen !== 'dxf')
      notificar(`${plano.codigo} subido`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setSubiendo(false)
    }
  }

  return (
    <div
      className="layout-planos"
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        setArrastrando(true)
      }}
      onDragLeave={() => setArrastrando(false)}
      onDrop={(e) => {
        if (!e.dataTransfer.types.includes('Files')) return
        e.preventDefault()
        setArrastrando(false)
        const fichero = e.dataTransfer.files?.[0]
        if (fichero) void subir(fichero)
      }}
    >
      <div className="rejilla-barra">
        {onVolver && (
          <button type="button" className="btn btn--sm" onClick={onVolver}>
            <ArrowLeft size={14} aria-hidden="true" />
            Volver a Mediciones
          </button>
        )}
        {planos.map((p) => {
          const Icono = ICONO_ORIGEN[p.origen]
          return (
            <button
              key={p.id}
              type="button"
              className={p.id === planoId ? 'btn btn--sm btn--primary' : 'btn btn--sm'}
              aria-pressed={p.id === planoId}
              onClick={() => {
                setPlanoId(p.id)
                setHojaObjetivo(undefined)
              }}
              title={`${p.codigo} · ${p.nombre}`}
            >
              <Icono size={14} aria-hidden="true" />
              {p.nombre}
              {/* Dos ficheros con el mismo nombre («DOCUMENTOS.pdf» dos veces)
                  dejaban dos pestañas idénticas: el código los distingue. */}
              <span className="muted">{p.codigo}</span>
            </button>
          )
        })}
        <button
          type="button"
          className="btn btn--sm"
          disabled={subiendo}
          onClick={() => inputRef.current?.click()}
          style={
            arrastrando
              ? { borderStyle: 'dashed', borderColor: 'var(--c-accent-strong)' }
              : { borderStyle: 'dashed' }
          }
        >
          <Upload size={14} aria-hidden="true" />
          {subiendo ? 'Subiendo…' : 'Soltar o elegir un plano'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ADMITIDOS}
          style={{ display: 'none' }}
          onChange={(e) => e.target.files?.[0] && void subir(e.target.files[0])}
        />
        {/* Fuera de la pestaña del plano y no dentro: una «x» dentro de un
            botón sería un botón dentro de otro, que no es HTML válido. */}
        {planoId && (
          <button
            type="button"
            className="btn btn--sm btn--danger btn--solo-icono"
            aria-label="Borrar este plano"
            title="Borrar este plano del presupuesto"
            onClick={() => void borrarPlano()}
          >
            <Trash2 size={14} aria-hidden="true" />
          </button>
        )}
        {partida && (
          <span className="rejilla-barra__ayuda muted">
            Lo que midas puede irse a «{partida.resumen}»
          </span>
        )}
      </div>

      <ErrorNotice error={error} />

      {!cargando && planos.length === 0 ? (
        <EmptyState title="Este presupuesto no tiene planos todavía">
          Suelta aquí un DXF, un PDF o una foto. El DXF se mide de un clic porque trae su
          geometría; un PDF o una foto los revisa la IA al subirlos, y desde ahí ya se puede
          medir encima.
        </EmptyState>
      ) : (
        planoId && (
          <VisorPlano
            planoId={planoId}
            hojaInicial={hojaObjetivo}
            aplicarA={
              partida
                ? { partidaId: partida.id, unidad: partida.unidad, resumen: partida.resumen, idsLineas }
                : undefined
            }
            onAplicado={() => {
              void cargarLineas()
              onAplicado?.()
            }}
            autoRevisarIa={revisarConIa}
            onRevisado={() => setRevisarConIa(false)}
          />
        )
      )}
    </div>
  )
}
